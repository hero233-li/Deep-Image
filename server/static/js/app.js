// Deep-Image App — 前端主逻辑
// 原则1：利于 DeepSeek 缓存命中 — reconstruct/chat 的 system prompt 固定不变

(function() {
var API = localStorage.getItem('deepImageApiBase') || (location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '');
var state = {
  mode:'exam',
  subject:'考研数学',
  model:'doubao',
  imageBase64:'',
  imageFile:null,
  filename:'',
  conversationId:'',
  rawVisionResult:'',
  reconstructedProblem:'',
  reconstructedGraphB64:'',
  questionIndex:1,
  backendReady:false,
  records:[]
};
var subjectsByMode = {
  exam:['考研数学','考研408','考研英语','考研政治']
};

function $(id){return document.getElementById(id)}
function setView(id){document.querySelectorAll('.view').forEach(function(v){v.classList.remove('active')});$(id).classList.add('active')}

// ---- Navigation ----
window.showModeView = function(){setView('modeView')};
window.showSpaceView = function(){renderSpace();setView('spaceView')};
window.enterMode = function(mode){state.mode='exam';state.subject='考研数学';renderSpace();setView('spaceView')};
window.openWrongBook = function(){renderSubjectSelect();setView('questionView');loadConversations()};

function renderSpace(){
  $('spaceTitle').textContent = '考研 Space';
  $('spaceSubtitle').textContent = '错题、识别、追问和复盘都留在数据库里。';
  $('spaceEyebrow').textContent = '更懂你的考研复盘';
  $('spaceHero').innerHTML = '欢迎来到 <span>Deep-Image 考研 Space</span>';
  $('subjectTabs').innerHTML = subjectsByMode[state.mode].map(function(s){
    return '<button class="subject-tab ' + (s===state.subject?'active':'') + '" data-subject="' + escapeHtml(s) + '">' + escapeHtml(s) + '</button>';
  }).join('');
  $('subjectTabs').querySelectorAll('.subject-tab').forEach(function(btn){
    btn.addEventListener('click', function(){ selectSubject(btn.getAttribute('data-subject')); });
  });
}
function selectSubject(subject){state.subject=subject;renderSpace()}
function renderSubjectSelect(){
  $('subjectSelect').innerHTML = subjectsByMode[state.mode].map(function(s){return '<option value="' + escapeHtml(s) + '">' + escapeHtml(s) + '</option>'}).join('');
  $('subjectSelect').value = state.subject;
  $('questionTitle').textContent = state.mode === 'exam' ? '错题集' : '代码问题集';
}
$('subjectSelect').addEventListener('change',function(){state.subject=this.value;loadConversations()});
$('modelSelect').addEventListener('change',function(){state.model=this.value});

// ---- Backend health ----
window.checkBackend = async function(){
  var btn = $('healthCheckBtn');
  if(btn){ btn.disabled = true; btn.textContent = '检测中'; }
  $('healthStatus').className='status checking';
  $('healthText').textContent='检测后端中';
  $('healthBanner').classList.remove('visible');
  $('healthBanner').innerHTML='';
  try{
    var ctrl=new AbortController();
    setTimeout(function(){ctrl.abort()},2500);
    var resp=await fetch(API + '/api/health',{signal:ctrl.signal});
    setHealth(resp.ok,resp.ok?'后端已连接':'后端异常');
  }catch(e){setHealth(false,'后端未启动')}
  finally{
    if(btn){ btn.disabled = false; btn.textContent = '重新检测'; }
  }
};
function setHealth(ok,msg){
  state.backendReady=ok;
  $('healthStatus').className='status ' + (ok?'ok':'bad');
  $('healthText').textContent=msg;
  $('healthBanner').classList.toggle('visible',!ok);
  $('healthBanner').innerHTML=ok?'':'后端服务未连接。请先进入 <code>server</code> 目录执行 <code>python3 run.py</code>。';
}
function requireBackend(){if(!state.backendReady){alert('后端服务未启动，请先进入 server 目录执行：python3 run.py');return false}return true}

// ---- Image handling ----
window.chooseImage = function(){if(!requireBackend())return;$('fileInput').click()};
$('fileInput').addEventListener('change',function(e){if(e.target.files.length)handleFile(e.target.files[0]);e.target.value=''});
var dz=$('dropZone');
dz.addEventListener('click',chooseImage);
dz.addEventListener('dragover',function(e){e.preventDefault();dz.classList.add('dragover')});
dz.addEventListener('dragleave',function(){dz.classList.remove('dragover')});
dz.addEventListener('drop',function(e){e.preventDefault();dz.classList.remove('dragover');if(e.dataTransfer.files.length)handleFile(e.dataTransfer.files[0])});
document.addEventListener('paste',function(e){
  var items=e.clipboardData&&e.clipboardData.items;if(!items)return;
  for(var i=0;i<items.length;i++){if(items[i].type.indexOf('image/')===0){e.preventDefault();handleFile(items[i].getAsFile());return}}
});

function handleFile(file){
  if(file.type.indexOf('image/')!==0){alert('请上传图片文件');return}
  if(file.size>10*1024*1024){alert('图片不能超过 10MB');return}
  state.imageFile=file;state.filename=file.name||'clipboard.png';state.imageBase64='';state.conversationId='';state.rawVisionResult='';state.reconstructedProblem='';
  $('fileName').textContent=state.filename;
  var reader=new FileReader();
  reader.onload=function(e){
    state.imageBase64=e.target.result.split(',')[1];
    $('previewImg').src=e.target.result;
    $('previewCard').classList.add('visible');
    $('dropZone').style.display='none';
    resetBlocks();
    $('visionBlock').textContent='图片已上传，点击"豆包识别"开始识别。';
  };
  reader.readAsDataURL(file);
}

function resetBlocks(){
  $('visionBlock').className='result-block empty';
  $('visionBlock').textContent='';
  $('visionBadge').style.display='none';
  $('copyVisionBtn').style.display='none';
  $('refreshVisionBtn').style.display='none';
  hideReconstruct();
}

// Image modal
$('previewImg').addEventListener('click',function(){openImageModal(this.src)});
function openImageModal(src){$('modalImg').src=src;$('imageModal').classList.add('visible');$('imageModal').setAttribute('aria-hidden','false')}
window.closeImageModal = function(){$('imageModal').classList.remove('visible');$('imageModal').setAttribute('aria-hidden','true')};
$('imageModal').addEventListener('click',function(e){if(e.target===this)closeImageModal()});
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeImageModal()});

// ---- Vision Recognition ----
window.recognizeImage = async function(forceRefresh){
  if(!requireBackend())return;
  if(!state.imageBase64){alert('请先上传图片');return}
  state.subject=$('subjectSelect').value;state.model=$('modelSelect').value;
  setLoading(true,forceRefresh?'豆包正在重新识别图片':'豆包正在识别图片');
  $('visionBtn').disabled=true;
  $('refreshVisionBtn').disabled=true;
  try{
    var resp=await fetch(API + '/api/vision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_base64:state.imageBase64,model_name:state.model,mode:state.mode,subject:state.subject,force_refresh:!!forceRefresh})});
    if(!resp.ok)throw new Error(await resp.text());
    var data=await resp.json();
    state.conversationId=data.conversation_id;
    state.rawVisionResult=data.vision_result || '';
    $('visionBlock').className='result-block';
    $('visionBlock').innerHTML=renderMarkdown(data.vision_result);
    $('visionBadge').style.display='inline-flex';
    $('visionBadge').textContent=forceRefresh?'已刷新':(data.from_cache?'来自缓存':'已入库');
    $('copyVisionBtn').style.display='inline-block';
    $('refreshVisionBtn').style.display='inline-block';
    // 显示还原按钮
    $('reconstructBtn').style.display='inline-block';
    uploadImageSilently();
    loadConversations();
    // 自动还原（如果没有已保存的还原结果）
    if(!state.reconstructedProblem) autoReconstruct();
  }catch(e){
    $('visionBlock').className='result-block';
    $('visionBlock').innerHTML='<span style="color:var(--red)">识别失败：'+escapeHtml(e.message)+'</span>';
  }finally{$('visionBtn').disabled=false;$('refreshVisionBtn').disabled=false;setLoading(false)}
};

async function uploadImageSilently(){
  if(!state.imageFile)return;
  var fd=new FormData();fd.append('file',state.imageFile);
  try{await fetch(API + '/api/upload',{method:'POST',body:fd})}catch(e){}
}

// ---- Reconstruct (题目还原) ----
window.reconstructProblem = async function(forceReconstruct){
  if(!state.rawVisionResult){alert('请先识别图片');return}
  if(!requireBackend())return;
  setLoading(true,forceReconstruct?'重新还原题目中':'正在还原题目');
  clearReconstructForLoading(forceReconstruct?'正在重新还原题目，请稍候':'正在还原题目，请稍候');
  $('reconstructBtn').disabled=true;
  $('reRefreshBtn').disabled=true;
  $('copyReconstructBtn').style.display='none';
  try{
    var resp=await fetch(API + '/api/reconstruct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vision_result:state.rawVisionResult,conversation_id:state.conversationId,mode:state.mode})});
    if(!resp.ok)throw new Error(await resp.text());
    var data=await resp.json();
    state.reconstructedProblem=data.problem;
    state.reconstructedGraphB64=data.graph_base64||'';
    renderReconstructResult(data.problem, data.graph_base64);
    $('reconstructBadge').style.display='inline-flex';
    $('reconstructBadge').textContent=forceReconstruct?'已重还原':'已还原';
    $('reRefreshBtn').style.display='inline-block';
    $('copyReconstructBtn').style.display='inline-block';
  }catch(e){
    $('reconstructBlock').className='result-block';
    $('reconstructBlock').innerHTML='<span style="color:var(--red)">还原失败：'+escapeHtml(e.message)+'</span>';
    $('reconstructTitle').style.display='flex';
    $('reconstructBlock').style.display='block';
  }finally{
    $('reconstructBtn').disabled=false;
    $('reRefreshBtn').disabled=false;
    setLoading(false);
  }
};

async function autoReconstruct(){
  clearReconstructForLoading('正在自动还原题目，请稍候');
  try{
    var resp=await fetch(API + '/api/reconstruct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vision_result:state.rawVisionResult,conversation_id:state.conversationId,mode:state.mode})});
    if(resp.ok){
      var data=await resp.json();
      state.reconstructedProblem=data.problem;
      state.reconstructedGraphB64=data.graph_base64||'';
      renderReconstructResult(data.problem, data.graph_base64);
      $('reconstructBadge').style.display='inline-flex';
      $('reconstructBadge').textContent='已还原';
      $('reRefreshBtn').style.display='inline-block';
      $('copyReconstructBtn').style.display='inline-block';
    }
  }catch(e){
    hideReconstruct();
  }
}

function hideReconstruct(){
  $('reconstructTitle').style.display='none';
  $('reconstructGraph').style.display='none';
  $('reconstructGraph').innerHTML='';
  $('reconstructBlock').style.display='none';
  $('reconstructBlock').innerHTML='';
  $('reconstructBadge').style.display='none';
  $('reRefreshBtn').style.display='none';
  $('copyReconstructBtn').style.display='none';
  $('reconstructBtn').style.display='none';
}

function clearReconstructForLoading(text){
  $('reconstructTitle').style.display='flex';
  $('reconstructGraph').style.display='none';
  $('reconstructGraph').innerHTML='';
  $('reconstructBlock').style.display='block';
  $('reconstructBlock').className='result-block';
  $('reconstructBlock').innerHTML='<div class="inline-loading"><span class="spinner"></span><span>'+escapeHtml(text)+'</span></div>';
  $('reconstructBadge').style.display='inline-flex';
  $('reconstructBadge').textContent='读取中';
}

// ---- Collapsible sections ----
window.toggleVision = function(){
  var block=$('visionBlock'),arrow=document.getElementById('visionArrow');
  block.classList.toggle('collapsed');
  if(arrow)arrow.classList.toggle('collapsed');
};
window.toggleReconstruct = function(){
  var block=$('reconstructBlock'),arrow=document.getElementById('reconstructArrow');
  block.classList.toggle('collapsed');
  if(arrow)arrow.classList.toggle('collapsed');
};

// ---- Chat ----
window.sendMessage = async function(){
  if(!requireBackend())return;
  var input=$('chatInput');var text=input.value.trim();if(!text)return;
  appendMessage('user',text);input.value='';input.style.height='auto';
  var loadingId='msg-'+Date.now();
  $('chatMessages').insertAdjacentHTML('beforeend','<div class="msg assistant" id="'+loadingId+'"><div class="avatar">D</div><div class="bubble"><span class="spinner"></span></div></div>');
  $('sendBtn').disabled=true;
  try{
    var payload={user_question:text,mode:state.mode,subject:$('subjectSelect').value,model_name:state.model};
    if(state.conversationId)payload.conversation_id=state.conversationId;
    else if(state.imageBase64)payload.image_base64=state.imageBase64;
    var resp=await fetch(API + '/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!resp.ok)throw new Error(await resp.text());
    var data=await resp.json();
    if(data.conversation_id)state.conversationId=data.conversation_id;
    $(loadingId).querySelector('.bubble').innerHTML=renderMarkdown(data.analysis_result);
    $(loadingId).removeAttribute('id');
    loadConversations();
  }catch(e){
    var el=$(loadingId);if(el)el.querySelector('.bubble').innerHTML='<span style="color:var(--red)">'+escapeHtml(e.message)+'</span>';
  }finally{$('sendBtn').disabled=false;$('chatInput').focus();scrollChat()}
};

function appendMessage(role,text){
  var a=role==='user'?'我':'D';
  $('chatMessages').insertAdjacentHTML('beforeend','<div class="msg '+role+'"><div class="avatar">'+a+'</div><div class="bubble">'+renderMarkdown(text)+'</div></div>');
  scrollChat();
}
function scrollChat(){$('chatMessages').scrollTop=$('chatMessages').scrollHeight}
$('chatInput').addEventListener('input',function(){this.style.height='auto';this.style.height=Math.min(this.scrollHeight,140)+'px'});

// ---- Conversation persistence ----
async function loadConversations(){
  if(!state.backendReady)return;
  try{
    var resp=await fetch(API + '/api/conversations?limit=50');if(!resp.ok)return;
    var data=await resp.json();
    var seen = {};
    state.records=(data.conversations||[]).filter(function(c){
      if(!(c.mode===state.mode && (!state.subject || c.subject===state.subject))) return false;
      var key = [c.mode || '', c.image_hash || c.id].join('|');
      if(seen[key]) return false;
      seen[key] = true;
      return true;
    });
    $('recordNotice').textContent='已从数据库读取 ' + state.records.length + ' 条记录。';
    renderQuestionList();
  }catch(e){$('recordNotice').textContent='读取数据库失败：' + e.message}
}

function renderQuestionList(){
  if(!state.records.length){$('questionList').innerHTML='<button class="question-item active">第 1 题</button>';return}
  $('questionList').innerHTML=state.records.map(function(r,i){
    var label='第 '+(i+1)+' 题';
    var cls=r.id===state.conversationId?' active':'';
    return '<button class="question-item'+cls+'" data-id="'+escapeHtml(r.id)+'" data-index="'+(i+1)+'">'+label+'</button>';
  }).join('');
  $('questionList').querySelectorAll('.question-item[data-id]').forEach(function(btn){
    btn.addEventListener('click', function(){
      restoreConversation(btn.getAttribute('data-id'), parseInt(btn.getAttribute('data-index'), 10));
    });
  });
}

async function restoreConversation(id,index){
  try{
    var resp=await fetch(API + '/api/conversation/' + id);if(!resp.ok)return;
    var c=await resp.json();
    state.conversationId=c.id;state.questionIndex=index;state.subject=c.subject||state.subject;state.mode=c.mode||state.mode;
    state.rawVisionResult=c.vision_result || '';
    state.reconstructedProblem=c.reconstructed || '';
    renderSubjectSelect();$('subjectSelect').value=state.subject;$('currentQuestionLabel').textContent='第 '+index+' 题';

    // 恢复图片
    if(c.image_base64){
      state.imageBase64=c.image_base64;
      $('previewImg').src='data:image/png;base64,' + c.image_base64;
      $('fileName').textContent='数据库题图';
      $('previewCard').classList.add('visible');
      $('dropZone').style.display='none';
      $('refreshVisionBtn').style.display='inline-block';
    }

    // 恢复识别结果
    if(c.vision_result){
      $('visionBlock').className='result-block';
      $('visionBlock').innerHTML=renderMarkdown(c.vision_result);
      $('visionBadge').style.display='inline-flex';
      $('visionBadge').textContent='数据库记录';
      $('copyVisionBtn').style.display='inline-block';
      $('reconstructBtn').style.display='inline-block';
    }

    // 恢复还原结果
    if(state.reconstructedProblem){
      renderReconstructResult(state.reconstructedProblem);
      $('reconstructBadge').style.display='inline-flex';
      $('reconstructBadge').textContent='已还原';
      $('reRefreshBtn').style.display='inline-block';
      $('copyReconstructBtn').style.display='inline-block';
    }

    // 恢复消息
    $('chatMessages').innerHTML='';(c.messages||[]).forEach(function(m){appendMessage(m.role,m.content)});
    renderQuestionList();
  }catch(e){}
}

window.jumpQuestion = function(){var n=parseInt($('jumpInput').value,10);if(n>0&&state.records[n-1])restoreConversation(state.records[n-1].id,n)};
window.newQuestion = function(){
  state.conversationId='';state.imageBase64='';state.imageFile=null;state.filename='';state.questionIndex=state.records.length+1;
  state.rawVisionResult='';state.reconstructedProblem='';
  $('currentQuestionLabel').textContent='第 '+state.questionIndex+' 题';
  $('previewCard').classList.remove('visible');$('previewImg').removeAttribute('src');
  $('dropZone').style.display='flex';
  resetBlocks();
  $('chatMessages').innerHTML='';$('chatInput').value='';renderQuestionList();
};

window.copyVisionResult = async function(){
  if(!state.rawVisionResult)return;
  try{await navigator.clipboard.writeText(state.rawVisionResult);var b=$('copyVisionBtn');b.textContent='已复制';setTimeout(function(){b.textContent='复制'},1200)}catch(e){alert('复制失败')}
};
window.exportPdf = function(){
  if(!state.conversationId){alert('请先识别图片');return}
  window.open(API + '/api/export/' + state.conversationId, '_blank');
};
window.copyReconstruct = async function(){
  if(!state.reconstructedProblem)return;
  try{await navigator.clipboard.writeText(state.reconstructedProblem);var b=$('copyReconstructBtn');b.textContent='已复制';setTimeout(function(){b.textContent='复制'},1200)}catch(e){alert('复制失败')}
};

function renderReconstructResult(problem, graphB64){
  var parsed = extractGraphSpec(problem || '');
  $('reconstructTitle').style.display='flex';
  $('reconstructBlock').style.display='block';
  $('reconstructBlock').className='result-block';
  $('reconstructBlock').innerHTML=renderMarkdown(parsed.text);

  // 优先使用后端 matplotlib 渲染的图
  if(graphB64){
    $('reconstructGraph').innerHTML='<img src="data:image/png;base64,'+graphB64+'" style="max-width:100%;border-radius:12px;border:1px solid var(--line)" alt="题目图形">';
    $('reconstructGraph').style.display='block';
  } else {
    // 回退到前端渲染
    var graphHtml = renderGraph(parsed.graph, parsed.text);
    if(graphHtml){
      $('reconstructGraph').innerHTML=graphHtml;
      $('reconstructGraph').style.display='block';
    } else {
      $('reconstructGraph').innerHTML='';
      $('reconstructGraph').style.display='none';
    }
  }
}

function extractGraphSpec(text){
  var graph = null;
  var cleaned = String(text || '').replace(/```deepimage-graph\s*([\s\S]*?)```/gi, function(_, jsonText){
    try { graph = JSON.parse(jsonText.trim()); } catch(e) {}
    return '';
  });
  return {text: cleaned.trim(), graph: graph};
}

function renderGraph(graph, text){
  var source = ((graph && JSON.stringify(graph)) || '') + '\n' + (text || '');
  var hasGeometry = graphHasGeometry(graph) || /圆|圆心|半径|切线|垂线|坐标系|角|弧/.test(source);
  var hasCurves = graphHasCurves(graph) || /函数图像|曲线|峰|零点|选项图|选项 A|选项A/.test(source);
  var html = '';
  if(graph && graph.type === 'function') hasCurves = true;
  if(graph && graph.type === 'geometry') hasGeometry = true;
  if(graph && graph.type === 'mixed'){hasGeometry = true;hasCurves = true}
  if(hasGeometry) html += renderGeometryGraph(graph || {});
  if(hasCurves) html += renderFunctionGraph(graph || {});
  return html;
}

function graphElements(graph){
  return graph && Array.isArray(graph.elements) ? graph.elements : [];
}

function graphHasGeometry(graph){
  return graphElements(graph).some(function(el){return el.kind && el.kind !== 'curve'});
}

function graphHasCurves(graph){
  return graphElements(graph).some(function(el){return el.kind === 'curve'});
}

function renderGeometryGraph(graph){
  var title = escapeHtml((graph && graph.title) || '图形示意');
  var elements = graphElements(graph);
  var points = collectGraphPoints(elements);
  var circles = elements.filter(function(el){return el.kind === 'circle'});
  var lines = elements.filter(function(el){return el.kind === 'line' || el.kind === 'segment'});
  if(!Object.keys(points).length) points = defaultGeometryPoints();
  if(!circles.length && points.O) circles = [{kind:'circle', label:'O', cx:points.O.x, cy:points.O.y, r:1}];
  if(!lines.length) lines = defaultGeometryLines(points);

  var bounds = graphBounds(points, circles);
  var map = graphMapper(bounds, 560, 340, 58);
  var svg = '<div class="graph-card"><div class="graph-title">'+title+'</div>' +
    '<svg class="diagram" viewBox="0 0 560 340" role="img" aria-label="'+title+'">' +
    '<defs><marker id="gArrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#6c625f"/></marker></defs>';

  circles.forEach(function(c){
    var center = map({x:num(c.cx, 0), y:num(c.cy, 0)});
    var edge = map({x:num(c.cx, 0) + num(c.r, 1), y:num(c.cy, 0)});
    var r = Math.abs(edge.x - center.x);
    svg += '<circle cx="'+center.x+'" cy="'+center.y+'" r="'+r+'" fill="#fff8f9" stroke="#ef3f52" stroke-width="3"/>';
  });

  lines.forEach(function(line){
    var a = pointFor(line.from, points), b = pointFor(line.to, points);
    if(!a || !b) return;
    var p1 = map(a), p2 = map(b);
    var dashed = line.style === 'dashed' ? ' stroke-dasharray="7 5"' : '';
    svg += '<line x1="'+p1.x+'" y1="'+p1.y+'" x2="'+p2.x+'" y2="'+p2.y+'" stroke="#2a2524" stroke-width="3"'+dashed+'/>';
  });

  elements.filter(function(el){return el.kind === 'angle'}).forEach(function(angle){
    var at = pointFor(angle.at, points), from = pointFor(angle.from, points), to = pointFor(angle.to, points);
    if(!at || !from || !to) return;
    var arc = angleArcPath(at, from, to, map, 34);
    svg += '<path d="'+arc+'" fill="none" stroke="#ef3f52" stroke-width="2"/>';
    var mid = map({x:(at.x + from.x * .42 + to.x * .42) / 1.84, y:(at.y + from.y * .42 + to.y * .42) / 1.84});
    svg += '<text x="'+mid.x+'" y="'+mid.y+'">'+escapeHtml(angle.label || '')+'</text>';
  });

  elements.filter(function(el){return el.kind === 'right_angle'}).forEach(function(el){
    var at = pointFor(el.at, points);
    if(!at) return;
    var p = map(at);
    svg += '<path d="M'+p.x+' '+p.y+' l0 -15 l15 0" fill="none" stroke="#2a2524" stroke-width="2"/>';
  });

  Object.keys(points).forEach(function(label){
    var p = map(points[label]);
    svg += '<circle cx="'+p.x+'" cy="'+p.y+'" r="5" fill="#2a2524"/>';
    svg += '<text x="'+(p.x + 8)+'" y="'+(p.y + 20)+'">'+escapeHtml(label)+'</text>';
  });

  svg += '</svg><div class="graph-note">DeepSeek 返回结构化图形指令，前端按点、线、圆、角和垂直标记渲染。</div></div>';
  return svg;
}

function renderFunctionGraph(graph){
  var title = escapeHtml((graph && graph.title) || '函数图像示意');
  var curves = graphElements(graph).filter(function(el){return el.kind === 'curve'});
  if(!curves.length) curves = [
    {label:'A', shape:'single_peak', peak_y:1, zeros:[0,1]},
    {label:'B', shape:'double_peak', peak_y:.5, zeros:[0,.5,1]},
    {label:'C', shape:'double_peak', peak_y:1, zeros:[0,.5,1]},
    {label:'D', shape:'single_peak', peak_y:1, zeros:[0,1]}
  ];
  return '<div class="graph-card"><div class="graph-title">'+title+' · 选项图像</div><div class="option-grid">' +
    curves.map(renderOptionCurve).join('') +
    '</div><div class="graph-note">DeepSeek 返回每个选项的曲线形状、峰值和零点，前端逐项渲染。</div></div>';
}

function collectGraphPoints(elements){
  var points = {};
  elements.forEach(function(el){
    if(el.kind === 'point' && el.label) points[el.label] = {x:num(el.x, 0), y:num(el.y, 0)};
  });
  elements.forEach(function(el){
    if(el.kind === 'circle' && el.label && !points[el.label]) points[el.label] = {x:num(el.cx, 0), y:num(el.cy, 0)};
  });
  // 不自动补点：垂足已由模型在 elements 中显式给出
  return points;
}

function defaultGeometryPoints(){
  return {O:{x:0,y:0}, C:{x:1,y:0}, B:{x:.62,y:.78}, D:{x:.62,y:0}, A:{x:1,y:1.1}};
}

function defaultGeometryLines(points){
  var lines = [
    {from:'O', to:'C', label:'OC'},
    {from:'O', to:'B', label:'OB'},
    {from:'B', to:'D', label:'BD'},
    {from:'C', to:'A', label:'CA'}
  ];
  return lines.filter(function(line){return points[line.from] && points[line.to]});
}

function graphBounds(points, circles){
  var xs = [], ys = [];
  Object.keys(points).forEach(function(k){xs.push(points[k].x);ys.push(points[k].y)});
  circles.forEach(function(c){
    var cx = num(c.cx, 0), cy = num(c.cy, 0), r = num(c.r, 1);
    xs.push(cx-r, cx+r);ys.push(cy-r, cy+r);
  });
  if(!xs.length){xs=[-1.2,1.2];ys=[-1.2,1.2]}
  var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
  var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
  if(maxX - minX < .2){minX -= 1;maxX += 1}
  if(maxY - minY < .2){minY -= 1;maxY += 1}
  return {minX:minX, maxX:maxX, minY:minY, maxY:maxY};
}

function graphMapper(bounds, width, height, pad){
  var sx = (width - pad * 2) / (bounds.maxX - bounds.minX);
  var sy = (height - pad * 2) / (bounds.maxY - bounds.minY);
  var s = Math.min(sx, sy);
  var ox = (width - (bounds.maxX - bounds.minX) * s) / 2;
  var oy = (height - (bounds.maxY - bounds.minY) * s) / 2;
  return function(p){
    return {x:round(ox + (p.x - bounds.minX) * s), y:round(height - oy - (p.y - bounds.minY) * s)};
  };
}

function pointFor(ref, points){
  if(!ref) return null;
  if(typeof ref === 'string') return points[ref] || null;
  if(typeof ref === 'object') return {x:num(ref.x, 0), y:num(ref.y, 0)};
  return null;
}

function angleArcPath(at, from, to, map, radius){
  function unit(p){var dx=p.x-at.x, dy=p.y-at.y, len=Math.sqrt(dx*dx+dy*dy)||1;return {x:dx/len,y:dy/len}}
  var u1 = unit(from), u2 = unit(to);
  var p1 = map({x:at.x + u1.x * .32, y:at.y + u1.y * .32});
  var p2 = map({x:at.x + u2.x * .32, y:at.y + u2.y * .32});
  return 'M'+p1.x+' '+p1.y+' A'+radius+' '+radius+' 0 0 0 '+p2.x+' '+p2.y;
}

function renderOptionCurve(curve){
  var label = escapeHtml(curve.label || '');
  var path = optionCurvePath(curve);
  return '<div class="option-card"><svg class="option-diagram" viewBox="0 0 220 150" role="img" aria-label="选项 '+label+'">' +
    '<line x1="28" y1="118" x2="202" y2="118" stroke="#6c625f" stroke-width="2"/>' +
    '<line x1="42" y1="128" x2="42" y2="24" stroke="#6c625f" stroke-width="2"/>' +
    '<text x="31" y="137">O</text><text x="188" y="137">π</text><text x="34" y="33">y</text>' +
    '<path d="'+path+'" fill="none" stroke="#2a2524" stroke-width="3.2" stroke-linecap="round"/>' +
    '</svg><div class="option-label">('+label+') '+escapeHtml(curve.shape || '')+'</div></div>';
}

function optionCurvePath(curve){
  var base = 118, left = 42, right = 192, width = right - left;
  var peakY = Math.max(0.15, Math.min(1, num(curve.peak_y, curve.shape === 'double_peak' ? .5 : 1)));
  var top = base - peakY * 82;
  if(Array.isArray(curve.points) && curve.points.length > 1){
    return curve.points.map(function(p,i){
      var x = left + num(p.x, 0) * width;
      var y = base - num(p.y, 0) * 82;
      return (i ? 'L' : 'M') + round(x) + ' ' + round(y);
    }).join(' ');
  }
  if(curve.shape === 'double_peak'){
    var mid = left + width / 2, q1 = left + width / 4, q3 = left + width * 3 / 4;
    return 'M'+left+' '+base+' C'+(left+18)+' '+top+' '+(q1-18)+' '+top+' '+q1+' '+top+
      ' C'+(q1+18)+' '+top+' '+(mid-18)+' '+base+' '+mid+' '+base+
      ' C'+(mid+18)+' '+top+' '+(q3-18)+' '+top+' '+q3+' '+top+
      ' C'+(q3+18)+' '+top+' '+(right-18)+' '+base+' '+right+' '+base;
  }
  if(curve.shape === 'increasing') return 'M'+left+' '+base+' C80 108 130 72 '+right+' '+top;
  if(curve.shape === 'decreasing') return 'M'+left+' '+top+' C90 60 140 100 '+right+' '+base;
  return 'M'+left+' '+base+' C80 '+top+' 150 '+top+' '+right+' '+base;
}

function num(value, fallback){
  var n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function round(value){
  return Math.round(value * 10) / 10;
}

// ---- Markdown ----
function renderMarkdown(md){
  if(!md)return '';
  md=normalizeLatex(md);
  // 先保护 LaTeX 块不被 escapeHtml 破坏
  var latexBlocks=[];
  md=md.replace(/\$\$([\s\S]*?)\$\$/g,function(_,t){latexBlocks.push('$$'+t+'$$');return'\x00LATEX'+ (latexBlocks.length-1)+'\x00'});
  md=md.replace(/\$([^$\n]+?)\$/g,function(_,t){latexBlocks.push('$'+t+'$');return'\x00LATEX'+ (latexBlocks.length-1)+'\x00'});
  md=md.replace(/\\\(([\s\S]*?)\\\)/g,function(_,t){latexBlocks.push('\\('+t+'\\)');return'\x00LATEX'+ (latexBlocks.length-1)+'\x00'});
  md=md.replace(/\\\[([\s\S]*?)\\\]/g,function(_,t){latexBlocks.push('\\['+t+'\\]');return'\x00LATEX'+ (latexBlocks.length-1)+'\x00'});
  var html=escapeHtml(md);
  // 恢复 LaTeX
  html=html.replace(/\x00LATEX(\d+)\x00/g,function(_,i){return latexBlocks[parseInt(i)]});
  html=html.replace(/```(\w*)\n?([\s\S]*?)```/g,function(_,lang,code){return '<pre><code>'+code.trim()+'</code></pre>'});
  html=html.replace(/`([^`]+)`/g,'<code>$1</code>');
  html=html.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  html=html.replace(/^### (.+)$/gm,'<h3>$1</h3>').replace(/^## (.+)$/gm,'<h2>$1</h2>').replace(/^# (.+)$/gm,'<h1>$1</h1>');
  html=html.replace(/^[\-\*] (.+)$/gm,'<li>$1</li>').replace(/((?:<li>.*?<\/li>\s*)+)/g,'<ul>$1</ul>');
  html=html.replace(/^&gt; (.+)$/gm,'<blockquote>$1</blockquote>');
  html=html.replace(/\n\n/g,'</p><p>');
  var result='<p>'+html+'</p>';
  // 渲染 MathJax
  setTimeout(function(){if(window.MathJax)MathJax.typesetPromise()},100);
  return result;
}

function normalizeLatex(text){
  return String(text || '')
    .replace(/boldsymbol\{([^{}]+)\}/g, '\\boldsymbol{$1}')
    .replace(/overarc\{([^{}]+)\}/g, '\\overarc{$1}')
    .replace(/\\boldsymbol\{([^{}]+)\}/g, '$1')
    .replace(/\\overarc\{([^{}]+)\}/g, '弧$1')
    .replace(/\\mathrm\{([^{}]+)\}/g, '$1')
    .replace(/\\text\{([^{}]+)\}/g, '$1')
    .replace(/\\left/g, '')
    .replace(/\\right/g, '')
    .replace(/\\,/g, ' ')
    .replace(/\\;/g, ' ');
}

function escapeHtml(str){var div=document.createElement('div');div.textContent=str||'';return div.innerHTML}
function setLoading(show,text){$('loading').classList.toggle('visible',show);$('loadingText').textContent=text||'处理中'}

// Init
checkBackend();renderSpace();
})();
