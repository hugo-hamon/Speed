import { call } from './api.js';
const $=id=>document.getElementById(id);
export function installLeaderboard(getState){
  let selected='normal',entries={},request=0,pending=false;
  function render(){
    $('rank-rows').replaceChildren();
    for(const entry of entries[selected]||[]){
      const row=document.createElement('tr');
      for(const value of [entry.name,`${entry.time.toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})} s`,`${entry.score} pts`]){
        const cell=document.createElement('td');cell.textContent=value;row.append(cell);
      }
      $('rank-rows').append(row);
    }
    $('rank-empty').hidden=!!entries[selected]?.length;
    $('rank-panel').setAttribute('aria-labelledby',`rank-${selected}`);
    for(const b of document.querySelectorAll('[data-rank]')){const active=b.dataset.rank===selected;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;}
  }
  function close(focus=false){
    $('leaderboard').hidden=true;
    if(getState().phase==='home')$('home-panel').hidden=false;
    if(focus)$('leaderboard-button').focus({preventScroll:true});
  }
  $('leaderboard-button').addEventListener('click',()=>{
    if(getState().phase!=='home')return;
    $('home-panel').hidden=true;$('leaderboard').hidden=false;
    refresh();$('leaderboard-back').focus({preventScroll:true});
  });
  $('leaderboard-back').addEventListener('click',()=>close(true));
  const tabs=[...document.querySelectorAll('[data-rank]')];
  tabs.forEach((button,i)=>{
    button.addEventListener('click',()=>{selected=button.dataset.rank;render();});
    button.addEventListener('keydown',e=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
      e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;tabs[j].click();tabs[j].focus();
    });
  });
  async function refresh(){
    const token=++request;
    try{const data=await call('get_leaderboard');if(token!==request)return;entries=data.entries;render();$('rank-error').textContent=data.warning||'';$('rank-error').hidden=!data.warning;}
    catch(e){if(token===request){$('rank-error').textContent=e.message;$('rank-error').hidden=false;}}
  }
  function reset(result){pending=false;$('ranking-form').reset();$('ranking-form').hidden=result.assisted;$('ranking-save').disabled=false;$('ranking-status').textContent=result.assisted?'Cette course terminée avec aide ne compte pas au classement.':'';}
  $('ranking-form').addEventListener('submit',async event=>{
    event.preventDefault();if(pending)return;
    const state=getState(),token=state.token,id=state.map.round_id;
    if(state.phase!=='result'||state.result?.assisted)return;
    pending=true;$('ranking-save').disabled=true;
    try{
      const data=await call('submit_leaderboard',id,$('player-name').value);
      if(getState().token!==token)return;
      entries=data.entries;render();$('ranking-form').hidden=true;$('ranking-status').textContent='Résultat enregistré. Retrouve le top 10 à l’accueil !';
    }catch(e){if(getState().token===token){$('ranking-status').textContent=e.message;$('ranking-save').disabled=false;}}
    finally{if(getState().token===token)pending=false;}
  });
  return {refresh,reset,close};
}
