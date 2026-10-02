/* Alto Padrão ERP — microinterações seguras e opcionais.
   Nenhum componente depende deste arquivo para aparecer ou funcionar. */
(function(){
  'use strict';
  function animateContainer(el){
    if(!el || el.dataset.uiMotionReady) return;
    el.dataset.uiMotionReady='1';
    if(typeof MutationObserver!=='function') return;
    const observer=new MutationObserver(function(mutations){
      mutations.forEach(function(m){
        Array.from(m.addedNodes||[]).forEach(function(node){
          if(!node || node.nodeType!==1) return;
          try{
            node.animate([
              {opacity:0,transform:'translateY(8px)'},
              {opacity:1,transform:'translateY(0)'}
            ],{duration:180,easing:'ease-out'});
          }catch(_){ }
        });
      });
    });
    observer.observe(el,{childList:true});
  }
  function initPurchaseForm(config){
    config=config||{};
    [config.items,config.activities,config.suppliers].forEach(function(selector){
      if(selector) animateContainer(document.querySelector(selector));
    });
  }
  window.UIEnhance={initPurchaseForm:initPurchaseForm};
})();
