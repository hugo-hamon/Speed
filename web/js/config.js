import { call } from './api.js';
const $=id=>document.getElementById(id);
const LEVELS={easy:'Facile',normal:'Normal',expert:'Expert'};

export function installConfig(onSaved) {
  let sizes=null, saving=false;
  function display(config) {
    $('map-source').value=config.map_source;
    const timing=config.ai_timing||{easy:12,normal:18,expert:24,message_seconds:3};
    for(const key of Object.keys(timing))$(`ai-time-${key}`).value=timing[key];
    $('size-options').replaceChildren();
    for(const [level,title] of Object.entries(LEVELS)) {
      const group=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=title;group.append(legend);
      for(const [id,size] of Object.entries(sizes)) {
        const label=document.createElement('label'),input=document.createElement('input'),text=document.createElement('span');
        input.type='checkbox';input.name=level;input.value=id;input.checked=config.sizes[level].includes(id);
        const name=document.createElement('strong'),detail=document.createElement('small');
        name.textContent=size.label;detail.textContent=`${size.width} × ${size.height} · ${size.width*size.height} carrefours`;
        text.append(name,detail);label.append(input,text);group.append(label);
      }
      $('size-options').append(group);
    }
    sourceChanged();
  }
  function selection() {
    return {ai_timing:Object.fromEntries(['easy','normal','expert','message_seconds'].map(key=>[key,Number($(`ai-time-${key}`).value)])),map_source:$('map-source').value,sizes:Object.fromEntries(Object.keys(LEVELS).map(level=>[level,[...$('size-options').querySelectorAll(`input[name="${level}"]:checked`)].map(input=>input.value)]))};
  }
  $('custom-add').addEventListener('click',()=>{
    if(!sizes||saving)return;
    const width=Number($('custom-width').value),height=Number($('custom-height').value);
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<3||height<3||width>30||height>30||width*height<12||width*height>750){problem('Choisis 3 à 30 intersections par côté, de 12 à 750 au total.');return;}
    const id=`custom_${width}x${height}`,config=selection();
    if(Object.keys(sizes).length>=20&&!sizes[id]){problem('Limite de 20 formats atteinte.');return;}
    sizes[id]={label:'Personnalisé',width,height};
    if(!config.sizes.normal.includes(id))config.sizes.normal.push(id);
    display(config);$('config-error').hidden=true;
  });
  function sourceChanged() {
    const authored=$('map-source').value==='authored';
    $('size-options').classList.toggle('inactive',authored);
    $('custom-add').disabled=authored;
    $('size-options').querySelectorAll('input').forEach(input=>{input.disabled=authored;});
    $('config-dialog').querySelector('.config-intro').textContent=authored?'Les douze villes du prototype restent disponibles, avec leur format de 12 carrefours.':'Choisis les formats possibles pour chaque difficulté. À chaque course, une taille est tirée au sort parmi tes choix.';
  }
  function problem(message) {$('config-error').textContent=message;$('config-error').hidden=false;}
  $('config-button').addEventListener('click',async()=>{
    $('config-dialog').showModal();$('config-save').disabled=true;$('config-error').hidden=true;
    try {const data=await call('get_config');sizes=data.board_sizes;display(data.config);if(data.warning)problem(data.warning);$('config-save').disabled=false;}
    catch(error){problem(error.message);}
  });
  $('config-close').addEventListener('click',()=>{if(!saving)$('config-dialog').close();});
  $('config-dialog').addEventListener('cancel',event=>{if(saving)event.preventDefault();});
  $('map-source').addEventListener('change',sourceChanged);
  $('config-reset').addEventListener('click',()=>{if(sizes&&!saving){display({map_source:'procedural',sizes:{easy:['small'],normal:['medium'],expert:['large']}});$('config-error').hidden=true;}});
  $('config-form').addEventListener('submit',async event=>{
    event.preventDefault();if(saving||!sizes)return;
    const allowed=Object.fromEntries(Object.keys(LEVELS).map(level=>[level,[...$('size-options').querySelectorAll(`input[name="${level}"]:checked`)].map(input=>input.value)]));
    if(Object.values(allowed).some(list=>!list.length)){problem('Choisis au moins une taille pour chaque difficulté.');return;}
    saving=true;$('config-save').disabled=true;$('config-error').hidden=true;
    try {await call('save_config',selection());$('config-dialog').close();await onSaved();}
    catch(error){problem(error.message);}
    finally {saving=false;$('config-save').disabled=false;}
  });
}
