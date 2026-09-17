import { useMemo } from 'react';
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType, type NodeProps, type Node, type Edge } from '@xyflow/react';
import dagre from '@dagrejs/dagre';
import { CheckCheck, GitBranch, ShieldCheck } from 'lucide-react';
import { Json, Step } from './api';
import { Badge, Empty } from './components';
import '@xyflow/react/dist/style.css';
type FlowData={label:string;skill:string;status:string;verification:boolean;alternatives:number;used:number;attempts:number;index:number};
function SkillNode({data,selected}:NodeProps<Node<FlowData>>){return <div className={`skill-node ${selected?'selected':''} ${data.verification?'verifier':''}`}><Handle type="target" position={Position.Left}/><div className="node-top"><span className="node-index">{String(data.index+1).padStart(2,'0')}</span><span>{data.verification?<><ShieldCheck size={13}/>目标验证</>:<><GitBranch size={13}/>原子技能</>}</span>{data.status==='succeeded'&&<CheckCheck size={15}/>}</div><strong title={data.label}>{data.label}</strong><code title={data.skill}>{data.skill}</code><div className="node-bottom"><Badge status={data.status}/><span>{data.alternatives?`替代 ${data.used}/${data.alternatives}`:data.attempts?`尝试 ${data.attempts}`:'未派发'}</span></div><Handle type="source" position={Position.Right}/></div>}
const nodeTypes={skill:SkillNode};
export function Flow({plan,states,selected,onSelect}:{plan:{steps:Step[];verification:string};states:Record<string,Json>;selected?:string;onSelect:(id:string)=>void}){
  const graph=useMemo(()=>{
    const g=new dagre.graphlib.Graph().setGraph({rankdir:'LR',nodesep:32,ranksep:68,marginx:28,marginy:24}).setDefaultEdgeLabel(()=>({}));
    plan.steps.forEach(s=>g.setNode(s.id,{width:224,height:134}));
    plan.steps.forEach(s=>(s.deps||[]).forEach(d=>g.setEdge(d,s.id)));dagre.layout(g);
    const nodes:Node<FlowData>[]=plan.steps.map((s,index)=>{const pos=g.node(s.id);const state=states[s.id]||{};const choice=[s,...(s.fallback||[])][state.alternative||0];return {id:s.id,type:'skill',position:{x:pos.x-112,y:pos.y-67},selected:s.id===selected,data:{label:s.id,skill:choice?.skill||s.skill,status:state.status||'pending',verification:s.id===plan.verification,alternatives:s.fallback?.length||0,used:state.alternative||0,attempts:state.attempts||0,index}}});
    const edges:Edge[]=plan.steps.flatMap(s=>(s.deps||[]).map(d=>({id:`${d}→${s.id}`,source:d,target:s.id,type:'smoothstep',markerEnd:{type:MarkerType.ArrowClosed,width:16,height:16},style:{stroke:states[d]?.status==='succeeded'?'#519787':'#b7c4c3',strokeWidth:1.7}})));
    return {nodes,edges};
  },[plan,states,selected]);
  if(!plan.steps.length)return <Empty title="没有可展示的步骤"/>;
  return <ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} onNodeClick={(_,n)=>onSelect(n.id)} nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} fitView fitViewOptions={{padding:.18}} minZoom={.2} maxZoom={1.8} proOptions={{hideAttribution:false}}><Background gap={22} size={1} color="#d7dfdd"/><Controls showInteractive={false}/><MiniMap nodeColor={n=>n.data.status==='succeeded'?'#4f9686':'#bac6c4'} maskColor="rgba(242,246,244,.65)" pannable zoomable/></ReactFlow>
}
