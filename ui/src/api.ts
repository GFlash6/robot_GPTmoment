import { useEffect, useState } from 'react';
export type Json = Record<string, any>;
export type Envelope<T> = {api_version:string; observed_at:string; data:T};
export type Page<T> = {items:T[]; total:number; offset:number; limit:number};
export type Step = {id:string; skill:string; args:Json; deps?:string[]; retries?:number; fallback?:{skill:string;args:Json}[]};
export type Task = {id:string; robot_id:string; goal?:string; status:string; priority:number; created_at:number; revision:number; generation:number; completed_steps?:number; step_count?:number; model_response_id?:string; plan:{steps:Step[];verification:string}; steps:Record<string,Json>; catalog:Record<string,Json>};
export type TaskDetail = {task:Task; executions:Json[]; control:Json|null; history:Json[]};
const base = (import.meta as unknown as {env:Record<string,string>}).env.VITE_API_BASE || '';
export async function get<T>(path:string, signal?:AbortSignal):Promise<Envelope<T>> {
  const controller=new AbortController();
  const cancel=()=>controller.abort();signal?.addEventListener('abort',cancel,{once:true});
  const timer=setTimeout(()=>controller.abort(),6000);
  try {
    const response = await fetch(`${base}/api/v1${path}`, {signal:controller.signal,headers:{Accept:'application/json'}});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error?.message || `请求失败 (${response.status})`);
    if(body.api_version!=='1' || !('data' in body)) throw new Error('观察 API 数据版本不兼容');
    return body;
  } catch(e) {
    if(controller.signal.aborted)throw new Error('请求超时或连接已中断');
    throw e;
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',cancel);}

}
export function useQuery<T>(path:string|null, interval=2000) {
  const [state,setState]=useState<{path:string|null; data?:T; observed?:string; error?:string; loading:boolean}>({path,loading:true});
  useEffect(()=>{
    if(!path){setState({path,loading:false});return;}
    let alive=true;let timer:ReturnType<typeof setTimeout>;const controller=new AbortController();
    setState({path,loading:true});
    const update=async()=>{
      try { const result=await get<T>(path,controller.signal);if(alive)setState({path,data:result.data,observed:result.observed_at,loading:false}); }
      catch(error){if(alive)setState(old=>({...old,path,loading:false,error:error instanceof Error?error.message:'无法连接观察服务'}));}
      finally {if(alive)timer=setTimeout(update,interval);}
    };
    void update();return()=>{alive=false;controller.abort();clearTimeout(timer);};
  },[path,interval]);
  return state.path===path?state:{path,loading:true};
}
export const statuses:Record<string,string>={queued:'排队中',pending:'待执行',accepted:'已接受',running:'执行中',succeeded:'已完成',failed:'失败',canceled:'已取消',canceling:'取消中',paused:'已暂停',pausing:'暂停中',unknown:'结果未知',replanning:'重规划中',dispatched:'已派发',requesting:'请求中',validated:'已校验',rejected:'已拒绝'};
export function stamp(value?:number|string|null){if(value==null)return '未记录';const date=new Date(typeof value==='number'?value*1000:value);return isNaN(date.getTime())?'时间不可解析':date.toLocaleString('zh-CN',{hour12:false});}
export function short(value:string){return value.length>15?value.slice(0,8)+'…'+value.slice(-4):value;}
export function bytes(value:number){if(!Number.isFinite(value))return '未记录';if(value<1024)return `${value} B`;if(value<1024**2)return `${(value/1024).toFixed(1)} KB`;return `${(value/1024**2).toFixed(1)} MB`;}
