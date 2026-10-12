'use strict';
async function requestJSON(url, method='GET', body=null){
  const headers={'Accept':'application/json'};
  if(method!=='GET'){headers['X-CSRF-Token']=window.csrfToken||'';if(body!==null)headers['Content-Type']='application/json';}
  const response=await fetch(url,{method,headers,credentials:'same-origin',body:body===null?undefined:JSON.stringify(body)});
  let payload;try{payload=await response.json();}catch{payload={detail:`HTTP ${response.status}`};}
  if(!response.ok){const detail=payload.detail;throw Error(typeof detail==='string'?detail:JSON.stringify(detail||payload));}
  return payload;
}
function showResult(text,bad=false,id='result'){
  const element=document.getElementById(id);if(!element)return;
  element.textContent=text;element.className=bad?'message alert':'message';
}
function formObject(form){return Object.fromEntries(new FormData(form).entries());}
function optionalInteger(value){return value?Number(value):null;}
async function execute(action){try{await action();}catch(err){showResult(err.message,true);}}
async function logout(){await execute(async()=>{await requestJSON('/api/auth/logout','POST');location.assign('/');});}
