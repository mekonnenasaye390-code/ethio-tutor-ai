const $ = s => document.querySelector(s), $$ = s => document.querySelectorAll(s);
const MODES = {
  tutor:{t:"AI Tutor", m:""},
  study:{t:"Study Materials", m:"Give clear study notes, a short summary and simple explanations for the topic."},
  exam:{t:"Exam Practice", m:"Create 5 practice exam questions on the topic, then give the answers with short explanations."},
  upload:{t:"Upload & Ask", m:"Answer questions about the attached PDF or image."},
  math:{t:"Math Solver", m:"Solve the math problem step by step and explain each step."},
  translate:{t:"Language Translation", m:"Translate the text into the selected language and add a pronunciation guide."},
  voice:{t:"Voice Assistant", m:"Keep answers short and easy to read aloud."},
  image:{t:"Image Understanding", m:"Describe and explain the attached image."},
  file:{t:"File Chat", m:"Answer questions using the attached document."}
};
let mode = "tutor", chat = [], file = null, speakBack = false;
let name = localStorage.getItem("etName") || "Mekonnen Asaye";
let hist = JSON.parse(localStorage.getItem("etHist") || "[]");

function show(v){ $$(".view").forEach(x=>x.classList.remove("on")); $("#v-"+v).classList.add("on"); }
function go(k){
  $$("aside nav a").forEach(a=>a.classList.toggle("on", a.dataset.go===k));
  if(k==="home"){ show("home"); renderRecent(); }
  else if(k==="history"){ show("history"); renderHist(); }
  else if(k==="settings"){ show("settings"); $("#nameIn").value=name; }
  else openChat(k);
}
function openChat(k){
  mode = k; chat = []; file = null; $("#fileTag").hidden = true; speakBack = (k==="voice");
  $("#ctitle").textContent = MODES[k].t; $("#msgs").innerHTML = "";
  add("a", "Hello "+name.split(" ")[0]+"! 👋 How can I help you today?");
  show("chat"); $("#msg").focus();
  if(["upload","image","file"].includes(k)) $("#file").click();
}
function esc(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function fmt(s){
  return esc(s).replace(/```(\w*)\n?([\s\S]*?)```/g,"<pre>$2</pre>").replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/^#+\s*(.+)$/gm,"<b>$1</b>");
}
function add(r, t){
  const d = document.createElement("div"); d.className = "m "+r;
  if(r==="a") d.innerHTML = fmt(t); else d.textContent = t;
  $("#msgs").appendChild(d); $("#msgs").scrollTop = 1e9; return d;
}
async function send(text){
  text = (text ?? $("#msg").value).trim(); if(!text) return;
  $("#msg").value = ""; add("u", text);
  chat.push({role:"user", text});
  if(chat.length===1){ hist.unshift({q:text, mode, time:Date.now()}); hist = hist.slice(0,50); localStorage.setItem("etHist", JSON.stringify(hist)); }
  const wait = add("a", "Thinking...");
  try{
    const r = await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({history:chat, language:$("#lang").value, mode:MODES[mode].m, file})});
    const raw = await r.text(); let j = {};
    try{ j = JSON.parse(raw); }catch(_){ throw new Error("Server did not answer. Run 'python app.py' and open http://127.0.0.1:5000 (not Live Server or the HTML file directly)."); }
    if(!r.ok) throw new Error(j.error || "Request failed");
    wait.innerHTML = fmt(j.reply); chat.push({role:"model", text:j.reply});
    if(speakBack && window.speechSynthesis) speechSynthesis.speak(new SpeechSynthesisUtterance(j.reply.replace(/[*#`]/g,"")));
  }catch(e){ wait.textContent = "⚠️ "+e.message; chat.pop(); }
  $("#msgs").scrollTop = 1e9;
}
function ago(t){ const m=Math.round((Date.now()-t)/60000); return m<1?"just now":m<60?m+" minutes ago":m<1440?Math.round(m/60)+" hours ago":Math.round(m/1440)+" days ago"; }
function items(list){
  return list.map((h,i)=>`<div class="act" data-i="${i}"><span>${esc(h.q)}<small>Answered • ${ago(h.time)}</small></span><em>✓</em></div>`).join("");
}
function renderRecent(){ $("#recent").innerHTML = hist.length ? items(hist.slice(0,4)) : "<p style='font-size:13px;color:#7b88a3'>No activity yet. Ask your first question!</p>"; }
function renderHist(){ $("#hlist").innerHTML = hist.length ? items(hist) : "<p>No history yet.</p>"; }

document.addEventListener("click", e=>{
  const t = e.target.closest("[data-tool]"); if(t){ go(t.dataset.tool); return; }
  const g = e.target.closest("[data-go]"); if(g){ go(g.dataset.go); return; }
  const a = e.target.closest(".act"); if(a){ go("tutor"); send(hist[a.dataset.i].q); }
});
$$("#langs a").forEach(a=>a.onclick=()=>{ const l=a.textContent.trim().split(" ").pop(); $("#lang").value=l; $$("#langs a").forEach(x=>x.classList.toggle("on",x===a)); });
$("#askBtn").onclick = ()=>{ const q=$("#q").value.trim(); if(!q) return; go("tutor"); $("#q").value=""; send(q); };
$("#q").onkeydown = e=>{ if(e.key==="Enter") $("#askBtn").click(); };
$("#send").onclick = ()=>send();
$("#msg").onkeydown = e=>{ if(e.key==="Enter") send(); };
$("#attach").onclick = ()=>$("#file").click();
$("#file").onchange = e=>{
  const f = e.target.files[0]; if(!f) return;
  const r = new FileReader();
  r.onload = ()=>{ file = {mime:f.type, data:r.result.split(",")[1]}; $("#fileTag").textContent="📎 "+f.name+" attached"; $("#fileTag").hidden=false; };
  r.readAsDataURL(f);
};
$("#mic").onclick = ()=>{
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SR) return alert("Voice input is not supported in this browser. Use Chrome or Edge.");
  const r = new SR(); r.lang = {Amharic:"am-ET",Tigrinya:"ti-ET",Oromo:"om-ET",Somali:"so-SO"}[$("#lang").value] || "en-US";
  r.onresult = e=>{ $("#msg").value = e.results[0][0].transcript; send(); };
  r.start();
};
$("#saveName").onclick = ()=>{ name=$("#nameIn").value.trim()||name; localStorage.setItem("etName",name); $("#uname").textContent=name; alert("Saved!"); };
$("#clear").onclick = ()=>{ hist=[]; localStorage.removeItem("etHist"); renderHist(); };
$("#uname").textContent = name; renderRecent();