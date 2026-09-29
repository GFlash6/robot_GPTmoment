"""Portable local-first robot inspection agent and operator UI."""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import re
import socket
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_REQUEST_BYTES = 12 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", re.DOTALL)


def system_snapshot() -> dict:
    """Return honest local runtime data; unavailable GPU fields stay unavailable."""
    snapshot = {
        "host": socket.gethostname(),
        "architecture": platform.machine(),
        "gpu": {"available": False},
    }
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        name, utilization, used, total, power = [
            item.strip() for item in completed.stdout.splitlines()[0].split(",")
        ]
        snapshot["gpu"] = {
            "available": True,
            "name": name,
            "utilization_percent": float(utilization),
            "memory_used_mib": float(used),
            "memory_total_mib": float(total),
            "power_w": None if power == "[N/A]" else float(power),
        }
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        pass
    return snapshot


@dataclass
class Step:
    skill: str
    status: str
    output: dict
    elapsed_ms: int


class AgentError(RuntimeError):
    pass


class InspectionAgent:
    """A deliberately small, evidence-first four-skill agent."""

    def __init__(self, evidence_root: Path | str = ".runtime/hackathon"):
        self.evidence_root = Path(evidence_root)
        self.model_endpoint = os.getenv(
            "MODEL_ENDPOINT", "http://127.0.0.1:8000/v1/chat/completions"
        )
        self.model_name = os.getenv(
            "MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"
        )
        self.model_api_key = os.getenv("MODEL_API_KEY", "")
        self.robot_skill_url = os.getenv("ROBOT_SKILL_URL", "")

    @staticmethod
    def plan(goal: str, destination: str) -> list[dict]:
        if not goal.strip():
            raise AgentError("goal is required")
        return [
            {"skill": "robot.navigate", "args": {"destination": destination.strip()}},
            {"skill": "vision.observe", "args": {}},
            {"skill": "inspection.assess", "args": {"goal": goal.strip()}},
            {"skill": "task.verify", "args": {}},
        ]

    def run(self, goal: str, destination: str, image_data_url: str) -> dict:
        task_id = str(uuid.uuid4())
        started = time.time()
        plan = self.plan(goal, destination)
        steps: list[Step] = []
        try:
            nav = self._timed("robot.navigate", self._navigate, destination.strip(), task_id)
            steps.append(nav)
            if nav.status == "failed":
                raise AgentError(nav.output["error"])

            observation = self._timed(
                "vision.observe", self._observe, image_data_url, task_id
            )
            steps.append(observation)
            assessment = self._timed(
                "inspection.assess", self._assess, goal.strip(), image_data_url
            )
            steps.append(assessment)
            verification = self._timed(
                "task.verify",
                self._verify,
                observation.output,
                assessment.output,
            )
            steps.append(verification)
            status = "succeeded"
            error = None
        except Exception as exc:  # Preserve the partial trace for operator review.
            status = "failed"
            error = str(exc)

        return {
            "task_id": task_id,
            "status": status,
            "goal": goal.strip(),
            "plan": plan,
            "steps": [asdict(step) for step in steps],
            "error": error,
            "elapsed_ms": round((time.time() - started) * 1000),
        }

    @staticmethod
    def _timed(skill: str, fn, *args) -> Step:
        started = time.time()
        try:
            output = fn(*args)
            status = output.pop("_step_status", "succeeded")
        except Exception as exc:
            output = {"error": str(exc)}
            status = "failed"
        return Step(skill, status, output, round((time.time() - started) * 1000))

    def _navigate(self, destination: str, task_id: str) -> dict:
        if not destination:
            return {
                "_step_status": "skipped",
                "reason": "current-position inspection; no destination supplied",
            }
        if not self.robot_skill_url:
            raise AgentError("ROBOT_SKILL_URL is required when destination is set")
        response = self._post_json(
            self.robot_skill_url,
            {
                "execution_id": f"{task_id}:navigate",
                "skill": "robot.navigate",
                "args": {"destination": destination},
            },
        )
        if response.get("status") != "succeeded":
            raise AgentError(f"robot.navigate did not succeed: {response.get('status', 'unknown')}")
        evidence = response.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise AgentError("robot.navigate succeeded without evidence")
        return response

    def _observe(self, image_data_url: str, task_id: str) -> dict:
        match = DATA_URL.match(image_data_url or "")
        if not match:
            raise AgentError("a JPEG, PNG, or WebP image is required")
        try:
            raw = base64.b64decode(match.group(2), validate=True)
        except ValueError as exc:
            raise AgentError("image is not valid base64") from exc
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise AgentError("image must be between 1 byte and 8 MiB")
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[
            match.group(1)
        ]
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        path = (self.evidence_root / f"{task_id}{suffix}").resolve()
        path.write_bytes(raw)
        return {"asset_path": str(path), "mime_type": match.group(1), "bytes": len(raw)}

    def _assess(self, goal: str, image_data_url: str) -> dict:
        prompt = (
            "You are a robot inspection model. Evaluate the image only against the user's goal. "
            "Return JSON only with this schema: "
            '{"status":"normal|anomaly|uncertain","summary":"...",'
            '"confidence":0.0,"findings":["..."]}. '
            "Do not claim anything that is not visible. User goal: " + goal
        )
        response = self._post_json(
            self.model_endpoint,
            {
                "model": self.model_name,
                "temperature": 0,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    }
                ],
            },
            bearer=self.model_api_key,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentError("model response has no assistant content") from exc
        if not isinstance(content, str):
            raise AgentError("model assistant content must be text")
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentError("model did not return valid JSON") from exc
        return result

    @staticmethod
    def _verify(observation: dict, assessment: dict) -> dict:
        required = {"status", "summary", "confidence", "findings"}
        if not required.issubset(assessment):
            raise AgentError("assessment is missing required fields")
        if assessment["status"] not in {"normal", "anomaly", "uncertain"}:
            raise AgentError("assessment status is invalid")
        confidence = assessment["confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise AgentError("assessment confidence must be between 0 and 1")
        if not isinstance(assessment["findings"], list):
            raise AgentError("assessment findings must be a list")
        asset_path = Path(observation.get("asset_path", ""))
        if not asset_path.is_file() or asset_path.stat().st_size != observation.get("bytes"):
            raise AgentError("observation evidence cannot be verified")
        return {
            "verified": True,
            "inspection_status": assessment["status"],
            "summary": assessment["summary"],
            "confidence": confidence,
            "evidence": [str(asset_path)],
        }

    @staticmethod
    def _post_json(url: str, payload: dict, bearer: str = "") -> dict:
        headers = {"Content-Type": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                body = response.read(MAX_REQUEST_BYTES)
        except HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", "replace")
            raise AgentError(f"upstream HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise AgentError(f"cannot reach upstream service: {exc.reason}") from exc
        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AgentError("upstream service returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise AgentError("upstream response must be a JSON object")
        return value


HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPTmoment for robot · Portable Physical Agent</title><style>
:root{color-scheme:dark;--ink:#f4f7f2;--muted:#a9b4ac;--dim:#909d93;--line:#283129;--panel:#101411;--panel2:#151a16;--black:#080a08;--green:#76b900;--green2:#b7e36f;--red:#ff746c;--amber:#e5b75e;font-family:"Aptos","Noto Sans SC",sans-serif;background:var(--black);color:var(--ink)}
*{box-sizing:border-box}::selection{background:var(--green);color:#071000}html{scrollbar-color:#415045 #0b0e0c}body{margin:0;background:var(--black);min-height:100vh}button,input,textarea{font:inherit}button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--green2);outline-offset:3px}
.shell{max-width:1500px;margin:auto;padding:0 28px 40px}.topbar{height:72px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:14px;font-weight:800;letter-spacing:-.02em}.mark{width:19px;height:19px;background:var(--green);box-shadow:7px 7px 0 #395b18}.brand span{color:var(--muted);font-weight:500}.runtime{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:13px}.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 12px rgba(118,185,0,.55)}
.intro{display:flex;justify-content:space-between;align-items:end;padding:38px 0 30px;gap:32px}.intro h1{font-size:clamp(36px,5vw,74px);line-height:.96;letter-spacing:-.04em;max-width:900px;margin:0;text-wrap:balance}.intro h1 em{color:var(--green2);font-style:normal}.intro p{max-width:360px;margin:0;color:var(--muted);line-height:1.6}
.telemetry{display:grid;grid-template-columns:1.6fr repeat(4,1fr);border:1px solid var(--line);border-radius:14px 14px 0 0;background:var(--panel)}.metric{padding:15px 18px;border-right:1px solid var(--line);min-width:0}.metric:last-child{border:0}.metric label{display:block;color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px}.metric strong{display:block;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.workbench{display:grid;grid-template-columns:minmax(260px,.78fr) minmax(420px,1.35fr) minmax(300px,.9fr);min-height:600px;border:1px solid var(--line);border-top:0;border-radius:0 0 14px 14px;overflow:hidden;background:var(--panel)}.column{padding:24px}.column+.column{border-left:1px solid var(--line)}.section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.section-title h2{font-size:15px;margin:0;letter-spacing:-.01em}.section-title span{font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}
.field{margin-bottom:18px}.field>label{display:block;color:var(--muted);font-size:12px;margin-bottom:8px}.field textarea,.field input[type=text]{width:100%;border:1px solid #354038;border-radius:10px;background:#0a0d0a;color:var(--ink);padding:12px 13px}.field textarea{height:108px;resize:vertical;line-height:1.5}.field input::placeholder,.field textarea::placeholder{color:#8b978e}.presets{display:flex;gap:7px;flex-wrap:wrap;margin:-4px 0 18px}.preset{width:auto;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--muted);padding:7px 10px;font-size:11px;cursor:pointer}.preset:hover{border-color:#536256;color:var(--ink)}
.upload{display:block;border:1px dashed #566158;border-radius:12px;padding:16px;cursor:pointer;background:#0b0e0c}.upload:hover,.upload:focus-within{border-color:var(--green);outline:2px solid var(--green2);outline-offset:3px}.upload strong{display:block;font-size:13px}.upload small{display:block;color:var(--dim);margin-top:5px}.upload input{position:absolute;opacity:0;pointer-events:none}.run{width:100%;border:0;border-radius:10px;padding:13px 16px;background:var(--green);color:#071000;font-weight:850;cursor:pointer;margin-top:6px;box-shadow:0 7px 22px rgba(47,76,11,.32)}.run:hover{background:#86c91c}.run:disabled{background:#40502f;color:#a7b19f;cursor:wait;box-shadow:none}
.vision{position:relative;min-height:470px;border:1px solid #222a23;background:#050705;overflow:hidden}.vision:before,.vision:after{content:"";position:absolute;width:28px;height:28px;border-color:var(--green);z-index:2}.vision:before{left:15px;top:15px;border-left:1px solid;border-top:1px solid}.vision:after{right:15px;bottom:15px;border-right:1px solid;border-bottom:1px solid}.vision #preview{width:100%;height:470px;display:none;background-position:center;background-repeat:no-repeat;background-size:contain}.empty{position:absolute;inset:0;display:grid;place-content:center;text-align:center;color:var(--dim);padding:30px}.empty strong{color:var(--muted);font-size:18px;margin-bottom:7px}.frame-meta{position:absolute;left:14px;bottom:14px;background:#080b08e8;border:1px solid #2a352c;padding:8px 10px;font:11px ui-monospace,monospace;color:var(--green2);display:none}.scan{position:absolute;left:0;right:0;height:1px;background:var(--green2);opacity:0;top:0;z-index:3}.processing .scan{opacity:.8;animation:scan 2.2s cubic-bezier(.16,1,.3,1) infinite}@keyframes scan{0%{top:0;opacity:0}12%{opacity:.75}88%{opacity:.75}100%{top:100%;opacity:0}}
.trace{display:grid;gap:0}.step{position:relative;display:grid;grid-template-columns:30px 1fr auto;gap:10px;align-items:center;padding:14px 0;border-bottom:1px solid #222923}.step-index{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;border:1px solid #3a443c;color:var(--dim);font:11px ui-monospace,monospace}.step b{display:block;font-size:13px}.step small{display:block;color:var(--dim);margin-top:3px}.step-status{font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}.step.succeeded .step-index{background:var(--green);border-color:var(--green);color:#071000}.step.failed .step-index{border-color:var(--red);color:var(--red)}.step.skipped .step-index{border-color:var(--amber);color:var(--amber)}
.verdict{margin-top:22px;padding-top:20px;border-top:1px solid var(--line)}.verdict-label{font-size:11px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase}.verdict h3{font-size:24px;line-height:1.1;margin:9px 0 7px;letter-spacing:-.025em}.verdict p{color:var(--muted);font-size:13px;line-height:1.5;margin:0}.confidence{margin-top:16px;display:flex;justify-content:space-between;color:var(--dim);font-size:11px}.confidence-track{height:3px;background:#252d27;margin-top:7px}.confidence-fill{height:100%;background:var(--green);transform:scaleX(0);transform-origin:left;transition:transform .7s cubic-bezier(.16,1,.3,1)}
details{margin-top:18px;border-top:1px solid var(--line);padding-top:14px}summary{cursor:pointer;color:var(--muted);font-size:12px}pre{white-space:pre-wrap;word-break:break-word;max-height:230px;overflow:auto;color:#aab7ac;font:11px/1.55 ui-monospace,monospace}.proof-strip{display:none}.footer{display:flex;justify-content:space-between;color:var(--dim);font-size:11px;padding:16px 2px}
@media(max-width:1050px){.workbench{grid-template-columns:1fr 1.25fr}.column:last-child{grid-column:1/-1;border-left:0;border-top:1px solid var(--line)}.trace{grid-template-columns:repeat(4,1fr);gap:14px}.step{grid-template-columns:30px 1fr;border:0}.step-status{grid-column:2}.telemetry{grid-template-columns:repeat(3,1fr)}.metric:nth-child(3){border-right:0}.metric:nth-child(n+4){border-top:1px solid var(--line)}}
@media(max-width:720px){.shell{padding:0 16px 28px}.topbar{min-height:76px;height:auto;padding:12px 0;flex-wrap:wrap;gap:10px}.brand span{display:none}.runtime span{display:inline;font-size:10px}.intro{display:block;padding:28px 0 22px}.intro p{margin-top:18px}.telemetry{grid-template-columns:1fr 1fr}.metric:nth-child(odd){border-right:1px solid var(--line)}.metric:nth-child(even){border-right:0}.metric:nth-child(n+3){border-top:1px solid var(--line)}.proof-strip{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-top:0;background:#0c100d}.proof-strip span{padding:10px 5px;text-align:center;color:var(--muted);font-size:9px;border-right:1px solid var(--line)}.proof-strip span:last-child{border:0}.workbench{display:block}.column+.column,.column:last-child{border-left:0;border-top:1px solid var(--line)}.column{padding:20px}.vision,.vision #preview{height:330px;min-height:330px}.trace{grid-template-columns:1fr}.footer{display:block}.footer span{display:block;margin-top:5px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}.processing .scan{animation:none;display:none}.confidence-fill{transition:none}}
</style></head><body><main class="shell">
<header class="topbar"><div class="brand"><i class="mark" aria-hidden="true"></i>GPTmoment for robot <span>/ Physical Agent</span></div><div class="runtime"><i class="dot" id="runtime-dot" aria-hidden="true"></i><span id="runtime-label">读取运行环境</span></div></header>
<section class="intro"><h1>让机器人在现场<em>看见、行动，拿证据回来。</em></h1><p id="intro-copy">模型、感知和证据在现场形成本地闭环；运行时可迁移到 DGX Spark、GPU 工作站或其他边缘节点。</p></section>
<section class="telemetry" aria-label="系统状态">
  <div class="metric"><label>GPU</label><strong id="gpu-name">正在读取设备</strong></div>
  <div class="metric"><label>GPU LOAD</label><strong id="gpu-load">—</strong></div>
  <div class="metric"><label>MEMORY</label><strong id="gpu-memory">—</strong></div>
  <div class="metric"><label>MODEL</label><strong id="model-name">—</strong></div>
  <div class="metric"><label>ROBOT</label><strong id="robot-state">—</strong></div>
</section>
<div class="proof-strip" aria-label="端侧证据链"><span>本地模型</span><span>4 SKILLS</span><span>原始证据</span><span>独立验证</span></div>
<section class="workbench">
  <form class="column" id="mission-form"><div class="section-title"><h2>任务指令</h2><span>MISSION INPUT</span></div>
    <div class="field"><label for="goal">告诉机器人要检查什么</label><textarea id="goal" required>检查当前区域的消防通道是否被物品占用</textarea></div>
    <div class="presets" aria-label="任务模板"><button class="preset" type="button" data-goal="检查当前区域的消防通道是否被物品占用">消防通道</button><button class="preset" type="button" data-goal="检查画面中的设备指示灯是否存在异常">设备状态</button><button class="preset" type="button" data-goal="检查货架是否存在明显缺货或摆放错位">货架巡检</button></div>
    <div class="field"><label for="destination">目的地</label><input id="destination" type="text" placeholder="留空即检查当前位置"></div>
    <div class="field"><label class="upload" for="image"><strong id="file-name">选择机器人相机图像</strong><small>JPEG / PNG / WebP，最大 8 MiB</small><input id="image" type="file" accept="image/png,image/jpeg,image/webp" required></label></div>
    <button class="run" id="run" type="submit">执行端侧巡检</button>
  </form>
  <section class="column"><div class="section-title"><h2>现场证据</h2><span id="frame-state">NO FRAME</span></div><div class="vision" id="vision"><div class="scan"></div><div class="empty" id="empty"><strong>等待视觉输入</strong><span>上传机器人当前画面后，原始图像会作为证据保存。</span></div><div id="preview" role="img" aria-label="机器人上传的现场画面"></div><div class="frame-meta" id="frame-meta">LOCAL EVIDENCE · ORIGINAL FRAME</div></div></section>
  <aside class="column"><div class="section-title"><h2>执行链</h2><span id="task-state" aria-live="polite">待命</span></div><div class="trace" id="steps"></div>
    <section class="verdict" aria-live="polite"><div class="verdict-label">Verifier verdict</div><h3 id="verdict-title">等待任务</h3><p id="verdict-copy">模型输出不会直接成为任务结论；结构与证据均通过校验后才会在这里显示。</p><div class="confidence"><span>置信度</span><span id="confidence-value">—</span></div><div class="confidence-track"><div class="confidence-fill" id="confidence-fill"></div></div></section>
    <details><summary>查看原始执行记录</summary><pre id="result">尚无执行记录。</pre></details>
  </aside>
</section>
<footer class="footer"><span>LOCAL-FIRST · PORTABLE RUNTIME · EVIDENCE-BASED</span><span id="host-state">LOCALHOST</span></footer>
</main><script>
const q=s=>document.querySelector(s), image=q('#image'), preview=q('#preview'), run=q('#run'), vision=q('#vision');let dataUrl='';
const skillCopy={"robot.navigate":["导航到目标区域","受控机器人适配器"],"vision.observe":["采集现场画面","保存原始视觉证据"],"inspection.assess":["理解巡检目标","本地视觉语言模型"],"task.verify":["核验证据与结论","独立完成验证"]};
const statusCopy={waiting:'等待',submitted:'已提交',succeeded:'完成',failed:'失败',skipped:'跳过'};
function renderSteps(steps=[]){const root=q('#steps');root.replaceChildren();Object.entries(skillCopy).forEach(([skill,copy],i)=>{const found=steps.find(s=>s.skill===skill),status=found?.status||'waiting',row=document.createElement('div');row.className=`step ${status}`;const index=document.createElement('span');index.className='step-index';index.textContent=String(i+1).padStart(2,'0');const body=document.createElement('div'),title=document.createElement('b'),sub=document.createElement('small');title.textContent=copy[0];sub.textContent=copy[1];body.append(title,sub);const state=document.createElement('span');state.className='step-status';state.textContent=found?`${statusCopy[status]||status} · ${found.elapsed_ms}ms`:statusCopy[status];row.append(index,body,state);root.append(row)})}
async function refreshSystem(){try{const [health,system]=await Promise.all([fetch('/api/health').then(r=>r.json()),fetch('/api/system').then(r=>r.json())]);q('#model-name').textContent=health.model;q('#robot-state').textContent=health.robot_configured?'CONNECTED':'CURRENT POSITION';q('#host-state').textContent=`${system.host} · ${system.architecture}`;q('#runtime-label').textContent=health.local_model?'LOCAL RUNTIME ONLINE':'REMOTE MODEL ENDPOINT';q('#runtime-dot').style.background=health.local_model?'var(--green)':'var(--amber)';if(system.gpu.available){q('#gpu-name').textContent=system.gpu.name;q('#gpu-load').textContent=`${system.gpu.utilization_percent}%`;q('#gpu-memory').textContent=`${Math.round(system.gpu.memory_used_mib/1024)} / ${Math.round(system.gpu.memory_total_mib/1024)} GB`}else{q('#gpu-name').textContent=`${system.architecture} · CPU/OTHER`;q('#gpu-load').textContent='—';q('#gpu-memory').textContent='—'}}catch{q('#gpu-name').textContent='系统状态离线';q('#runtime-label').textContent='RUNTIME OFFLINE';q('#runtime-dot').style.background='var(--red)'}}
document.querySelectorAll('.preset').forEach(button=>button.onclick=()=>{q('#goal').value=button.dataset.goal});
image.onchange=()=>{const file=image.files[0];if(!file)return;const reader=new FileReader;reader.onload=()=>{dataUrl=reader.result;preview.style.backgroundImage=`url(${JSON.stringify(dataUrl)})`;preview.style.display='block';q('#empty').style.display='none';q('#frame-meta').style.display='block';q('#frame-state').textContent=`${file.type.replace('image/','').toUpperCase()} · ${(file.size/1024).toFixed(0)} KB`;q('#file-name').textContent=file.name};reader.readAsDataURL(file)};
q('#mission-form').onsubmit=async event=>{event.preventDefault();if(!dataUrl){q('#verdict-title').textContent='缺少现场图像';q('#verdict-copy').textContent='请先上传机器人相机画面，再执行巡检。';image.focus();return}run.disabled=true;run.textContent='本地模型推理中…';vision.classList.add('processing');q('#task-state').textContent='执行中';q('#verdict-title').textContent='正在分析现场';q('#verdict-copy').textContent='任务已提交，等待四个 Skill 返回真实状态。';renderSteps(Object.keys(skillCopy).map(skill=>({skill,status:'submitted',elapsed_ms:0})));try{const response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({goal:q('#goal').value,destination:q('#destination').value,image:dataUrl})}),out=await response.json();renderSteps(out.steps||[]);q('#result').textContent=JSON.stringify(out,null,2);q('#task-state').textContent=out.status==='succeeded'?'完成':'失败';const verification=(out.steps||[]).find(s=>s.skill==='task.verify')?.output;if(out.status==='succeeded'&&verification){const labels={normal:'未发现异常',anomaly:'发现异常',uncertain:'需要人工复核'};q('#verdict-title').textContent=labels[verification.inspection_status]||'巡检完成';q('#verdict-copy').textContent=verification.summary;q('#confidence-value').textContent=`${Math.round(verification.confidence*100)}%`;q('#confidence-fill').style.transform=`scaleX(${verification.confidence})`}else{q('#verdict-title').textContent='任务未完成';q('#verdict-copy').textContent=out.error||'检查原始执行记录获取原因。';q('#confidence-value').textContent='—';q('#confidence-fill').style.transform='scaleX(0)'}}catch(error){q('#task-state').textContent='连接失败';q('#verdict-title').textContent='无法连接运行时';q('#verdict-copy').textContent=String(error)}finally{run.disabled=false;run.textContent='再次执行巡检';vision.classList.remove('processing');refreshSystem()}};
renderSteps();refreshSystem();setInterval(refreshSystem,3000);
</script></body></html>"""


def make_handler(agent: InspectionAgent):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self._reply(200, HTML, "text/html; charset=utf-8")
            elif self.path == "/api/health":
                model_host = (urlparse(agent.model_endpoint).hostname or "").lower()
                self._json(200, {"status": "ok", "model": agent.model_name, "local_model": model_host in {"127.0.0.1", "localhost", "::1"}, "robot_configured": bool(agent.robot_skill_url)})
            elif self.path == "/api/system":
                self._json(200, system_snapshot())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/run":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise AgentError("request body must be between 1 byte and 12 MiB")
                payload = json.loads(self.rfile.read(length))
                result = agent.run(
                    str(payload.get("goal", "")),
                    str(payload.get("destination", "")),
                    str(payload.get("image", "")),
                )
                self._json(200, result)
            except (AgentError, json.JSONDecodeError, TypeError) as exc:
                self._json(400, {"status": "failed", "error": str(exc)})

        def _json(self, status: int, value: dict):
            self._reply(status, json.dumps(value, ensure_ascii=False), "application/json; charset=utf-8")

        def _reply(self, status: int, value: str, content_type: str):
            body = value.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            if self.path in {"/api/health", "/api/system"}:
                return
            print(f"[{self.log_date_time_string()}] {fmt % args}")

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3030)
    parser.add_argument("--evidence-root", default=".runtime/hackathon")
    args = parser.parse_args(argv)
    agent = InspectionAgent(args.evidence_root)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(agent))
    print(f"GPTmoment for robot Physical Agent: http://{args.host}:{args.port}")
    print(f"Model: {agent.model_name} @ {agent.model_endpoint}")
    server.serve_forever()


if __name__ == "__main__":
    main()
