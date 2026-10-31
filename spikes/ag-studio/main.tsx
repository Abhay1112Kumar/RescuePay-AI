import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AgStudio, createWidgets, type AgWidgetDefinition } from 'ag-studio-react'
import type { AgDefaultRegistry, AgReportState, AgWidgetData, AgWidgetDataFormat } from 'ag-studio'
interface InvestigationState extends AgWidgetData<Record<string, never>, AgWidgetDataFormat<unknown>> { type: 'investigation' }
type InvestigationDef = AgWidgetDefinition<'investigation', InvestigationState>
interface InvestigationRegistry extends Omit<AgDefaultRegistry, 'widgets'> { widgets: readonly [...AgDefaultRegistry['widgets'], InvestigationDef] }
const records = [
 { label:'Synthetic uncertain capture', state:'CAPTURE_UNCERTAIN', freshness:'Stored only', action:'Manual reconciliation' },
 { label:'Synthetic pending settlement', state:'CAPTURE_PENDING', freshness:'Stored only', action:'Wait / check status' },
 { label:'Synthetic historical completed', state:'COMPLETED', freshness:'Not checked now', action:'Review record' },
]
function InvestigationWidget() {
 const [uncertainOnly,setUncertainOnly]=useState(false)
 const visible=records.filter((r)=>!uncertainOnly || r.state==='CAPTURE_UNCERTAIN')
 return <section style={{padding:24,fontFamily:'system-ui',overflow:'auto',height:'100%',boxSizing:'border-box',background:'#f8f5ff'}}>
 <h2>Payment investigation · synthetic only</h2><p>No PayPal data, AI, payment controls or external services.</p>
 <button onClick={()=>setUncertainOnly(!uncertainOnly)}>{uncertainOnly?'Show all scenarios':'Show uncertain payments'}</button>
 <p role="status">{visible.length} synthetic records shown</p>
 <ul>{visible.map((r)=><li key={r.state}><strong>{r.label}</strong><p>{r.state} · {r.freshness} · {r.action}</p></li>)}</ul>
 </section>
}
const definition: InvestigationDef = {id:'investigation',label:'Payment investigation',dataMapping:{},form:(params)=>params.createDefaults({dataMappingItems:[]}),comp:InvestigationWidget,defaultSize:{width:700,height:450},minSize:{width:300,height:250}}
const widgets=createWidgets<InvestigationRegistry>({additionalTypes:[definition],menu:[{label:'RescuePay spike',widgetIds:['investigation']}]})
const initialState: AgReportState<InvestigationRegistry> = {pages:[{id:'investigation-page',widgets:{investigation:{type:'investigation',dataMapping:{}}},widgetLayout:{investigation:{xTrack:0,yTrack:0,xSpan:24,ySpan:16}}}],selectedPageId:'investigation-page'}
createRoot(document.getElementById('root')!).render(<main style={{height:'100vh',display:'flex',flexDirection:'column',fontFamily:'system-ui'}}><h1 style={{fontSize:20}}>AG Studio isolated evaluation — synthetic data only</h1><p>No licence key/trial activated. Evaluation warnings may appear. Not part of the main application.</p><div style={{flex:1,minHeight:500}}><AgStudio<InvestigationRegistry> data={{sources:[{id:'payments',data:records}]}} widgets={widgets} initialState={initialState} mode="view" /></div></main>)
