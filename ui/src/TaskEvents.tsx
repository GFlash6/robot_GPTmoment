import { useEffect, useRef, useState } from 'react';
import { Json } from './api';
import { Raw } from './components';

const labels: Record<string, string> = { submitted: '任务已提交', dispatch_intent: '执行派发记录',
  execution_result: '执行结果', execution_unknown: '执行状态未知', input_rejected: '输入被拒绝',
  interrupt_requested: '收到控制请求', command_applied: '命令已应用' };

export function TaskEvents({ call, suggestedTaskId }: { call: (name: string, args: Json) => Promise<Json>; suggestedTaskId?: string }) {
  const api = useRef(call); api.current = call;
  const [tasks, setTasks] = useState<Json[]>([]);
  const [selected, setSelected] = useState('');
  const [listError, setListError] = useState('');
  const [listLoaded, setListLoaded] = useState(false);
  const [listRevision, setListRevision] = useState(0);
  const [listBusy, setListBusy] = useState(false);
  const [view, setView] = useState<{ task: string; events: Json[]; more: boolean; loading: boolean; error: string }>({ task: '', events: [], more: false, loading: false, error: '' });
  const refresh = useRef<() => void>(() => {});
  useEffect(() => {
    let active = true;
    setListBusy(true);
    void api.current('task.list', {}).then(result => {
      if (!active) return;
      setTasks(result.items); setListLoaded(true); setListError('');
      setSelected(old => result.items.some((t: Json) => t.id === suggestedTaskId) ? suggestedTaskId! :
        result.items.some((t: Json) => t.id === old) ? old : result.items[0]?.id || '');
    }).catch(e => { if (active) setListError(e instanceof Error ? e.message : '任务列表读取失败'); })
      .finally(() => { if (active) setListBusy(false); });
    return () => { active = false; };
  }, [suggestedTaskId, listRevision]);

  useEffect(() => {
    let active = true, running = false, more = false, cursor = 0;
    let upper: number | undefined;
    let events: Json[] = [];
    setView({ task: selected, events: [], more: false, loading: !!selected, error: '' });
    const read = async (manual = false) => {
      if (!selected || running || (more && !manual)) return;
      running = true;
      setView(v => ({ ...v, loading: true }));
      try {
        const page = await api.current('task.events-page', { task_id: selected, after_seq: cursor, limit: 50,
          ...(upper === undefined ? {} : { through_seq: upper }) });
        if (!active) return;
        let previous = cursor;
        if (page.task_id !== selected || !Array.isArray(page.events) || typeof page.has_more !== 'boolean' ||
            !Number.isSafeInteger(page.through_seq) || page.through_seq < cursor ||
            (upper !== undefined && page.through_seq !== upper)) throw new Error('事件分页校验失败，请重新选择任务后读取。');
        for (const event of page.events) {
          if (event.task !== selected || !Number.isSafeInteger(event.seq) || event.seq <= previous || event.seq > page.through_seq)
            throw new Error('事件顺序校验失败，已保留上次记录。');
          previous = event.seq;
        }
        if (page.next_seq !== previous || (page.has_more && !page.events.length)) throw new Error('事件游标未推进，已保留上次记录。');
        events = [...events, ...page.events]; cursor = page.next_seq; more = page.has_more;
        upper = more ? page.through_seq : undefined;
        setView({ task: selected, events, more, loading: false, error: '' });
      } catch (e) {
        if (active) setView(v => ({ ...v, loading: false, error: e instanceof Error ? e.message : '事件读取失败' }));
      } finally { running = false; }
    };
    refresh.current = () => { void read(true); };
    void read();
    const timer = setInterval(() => { void read(); }, 2500);
    return () => { active = false; clearInterval(timer); refresh.current = () => {}; };
  }, [selected]);

  const shown = view.task === selected ? view.events : [];
  return <section className="panel workbench-events" aria-label="任务事件记录">
    <h2>任务事件记录</h2>
    <p>按发生顺序读取实际账本。刷新记录不会重新执行任务。</p>
    <label htmlFor="workbench-event-task">查看任务</label><select id="workbench-event-task" value={selected} onChange={e => setSelected(e.target.value)} disabled={!tasks.length}>
      {!tasks.length && <option value="">{listError ? '任务列表读取失败' : listLoaded ? '暂无可读取任务' : '正在读取任务列表'}</option>}
      {tasks.map(task => <option key={task.id} value={task.id}>{task.robot_id} · {task.id.slice(0, 12)}</option>)}
    </select>
    <button disabled={listBusy} onClick={() => setListRevision(v => v + 1)}>重新读取任务列表</button>
    {selected && <code className="workbench-event-task">{selected}</code>}
    {listError && <p className="workbench-error" role="alert">{listError}。请重新读取任务列表。</p>}
    {view.error && <p className="workbench-error" role="alert">{view.error}。已保留上次成功读取的记录，可刷新事件重试。</p>}
    {selected && <div className="workbench-buttons"><button disabled={view.loading} onClick={() => refresh.current()}>{view.more ? '加载后续事件' : '刷新事件'}</button><span>{view.loading ? '正在读取…' : `已读取 ${shown.length} 条事件`}</span></div>}
    {!selected && listLoaded && !listError && <p>提交实际任务后，可在这里查看执行过程。</p>}
    {selected && !view.loading && !view.error && !shown.length && <p>该任务尚无事件记录。</p>}
    <ol className="workbench-event-list">{shown.map(event => <li key={event.seq}>
      <div><strong>{labels[event.type] || event.type}</strong><span>#{event.seq} · {new Date(event.ts * 1000).toLocaleString()}</span></div>
      <Raw value={event.data} label="查看事件证据" />
    </li>)}</ol>
  </section>;
}
