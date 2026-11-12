(function(){
  'use strict';
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const stage=$('#stage'), telas=$$('.tela'), wipe=$('#wipe'), prog=$('#prog i'), cont=$('#cont'), capTxt=$('#capTxt');
  const SVGNS='http://www.w3.org/2000/svg';
  // ?pdf=1: cada tela já no estado final, sem transição nem temporizador (usado para gerar o PDF)
  const modoPdf=new URLSearchParams(location.search).has('pdf');
  if(modoPdf)document.documentElement.classList.add('pdf');
  const reduz=matchMedia('(prefers-reduced-motion: reduce)').matches||modoPdf;
  let atual=0, escalaAtual=1, emTransicao=false, pendente=null;
  const total=telas.length, dd=n=>String(n).padStart(2,'0');
  const autos={};let autoAtivos=[]; // temporizador dos botões (ver mais abaixo)

  /* ---------------------------------------------------------- miolo: o conteúdo de cada tela encolhe por igual, centralizado,
     e o fundo continua ocupando a tela inteira (o que tem a classe sangra fica fora do miolo) */
  telas.forEach(t=>{
    const m=document.createElement('div');m.className='miolo';
    [...t.childNodes].forEach(n=>{if(!(n.nodeType===1&&n.classList.contains('sangra')))m.appendChild(n);});
    t.appendChild(m);
  });

  /* ---------------------------------------------------------- palco */
  function escala(){
    escalaAtual=Math.min(innerWidth/1600,innerHeight/900);
    stage.style.transform='scale('+escalaAtual+')';
  }
  addEventListener('resize',escala);escala();

  /* ---------------------------------------------------------- contadores */
  function contar(el){
    const alvo=parseFloat(el.dataset.conta),casas=+el.dataset.casas||0,t0=performance.now(),dur=1300;
    const fmt=new Intl.NumberFormat('pt-BR',{minimumFractionDigits:casas,maximumFractionDigits:casas});
    if(reduz){el.textContent=fmt.format(alvo);return;}
    (function passo(t){const p=Math.min(1,(t-t0)/dur),v=alvo*(1-Math.pow(1-p,3));el.textContent=fmt.format(v);if(p<1)requestAnimationFrame(passo);})(t0);
  }

  /* ---------------------------------------------------------- navegação */
  const aoEntrar={};
  function aplicar(n){
    telas[atual].querySelectorAll('video').forEach(v=>v.pause());
    pararAutos();
    telas[atual].classList.remove('ativa');
    atual=n;const t=telas[n];
    t.classList.add('ativa');
    stage.className='t-'+({claro:'claro',claro2:'claro',escuro:'escuro',lime:'lime',foto:'foto'}[t.dataset.tema]||'escuro')+(n===0?' capa':'');
    capTxt.textContent=t.dataset.cap||'';
    prog.style.width=((n+1)/total*100)+'%';
    cont.textContent=dd(n+1);
    $('#ant').disabled=n===0;$('#prox').disabled=n===total-1;
    t.querySelectorAll('[data-conta]').forEach(contar);
    $$('#sumLista button').forEach(b=>b.classList.toggle('atual',+b.dataset.i===n));
    history.replaceState(null,'','#'+(n+1));
    const fn=aoEntrar[t.classList[1]];if(fn)fn(t);
    iniciarAutos(t);
  }
  function ir(n){
    n=Math.max(0,Math.min(total-1,n));
    if(emTransicao){pendente=n;return;}
    if(n===atual)return;
    if(reduz||!wipe.animate){aplicar(n);return;}
    /* transição de cinema (05/11, noite): faixas pretas de tela larga fecham, a tela sai com zoom e desfoque
       e a nova entra do escuro, se assentando. A dos capítulos e das capas de marca é mais lenta. */
    const dir=n>atual?1:-1, velha=telas[atual], nova=telas[n];
    const forte=/s-cap|s-cm|s-cine|s-arcta/.test(nova.className);
    let cine=$('#cine');
    if(!cine){cine=document.createElement('div');cine.id='cine';cine.innerHTML='<i></i><i></i>';stage.appendChild(cine);}
    const [b1,b2]=cine.children;
    emTransicao=true;
    const ease='cubic-bezier(.65,0,.25,1)', t1=forte?520:380, t2=forte?950:620;
    const fim=()=>{emTransicao=false;if(pendente!==null){const p=pendente;pendente=null;ir(p);}};
    [b1,b2].forEach(b=>b.animate([{transform:'scaleY(0)'},{transform:'scaleY(1)'}],{duration:t1,easing:ease,fill:'forwards'}));
    velha.animate([{transform:'scale(1) translateX(0)',filter:'blur(0) brightness(1)'},{transform:`scale(1.07) translateX(${-dir*2}%)`,filter:'blur(10px) brightness(.15)'}],{duration:t1,easing:ease}).onfinish=()=>{
      aplicar(n);
      nova.animate([{transform:`scale(${forte?1.16:1.08}) translateX(${dir*2}%)`,filter:'blur(12px) brightness(.15)'},{transform:'scale(1) translateX(0)',filter:'blur(0) brightness(1)'}],{duration:t2,easing:'cubic-bezier(.2,.75,.2,1)'});
      [b1,b2].forEach(b=>b.animate([{transform:'scaleY(1)'},{transform:'scaleY(0)'}],{duration:t2,delay:forte?180:60,easing:ease,fill:'forwards'}));
      setTimeout(fim,t2*.7);
    };
  }
  addEventListener('hashchange',()=>{const n=parseInt(location.hash.slice(1),10);if(!isNaN(n))ir(n-1);});
  $('#ant').addEventListener('click',e=>{e.stopPropagation();ir(atual-1);});
  $('#prox').addEventListener('click',e=>{e.stopPropagation();ir(atual+1);});
  // data-ir aponta para o id da tela (ou o número dela, contado de 1)
  const indice=v=>/^\d+$/.test(v)?+v-1:telas.findIndex(t=>t.id===v);
  $$('[data-ir]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();ir(indice(b.dataset.ir));}));

  /* sumário */
  const sum=$('#sumario'), lista=$('#sumLista');
  let capAnt='';
  telas.forEach((t,i)=>{
    const c=(t.dataset.cap||'').match(/^\((\d+)\) (.*)$/);
    if(c&&c[1]!==capAnt){capAnt=c[1];const h=document.createElement('li');h.className='cap-s';h.textContent=c[1]+' · '+c[2];lista.appendChild(h);}
    if(t.classList.contains('s-cap'))return;
    const li=document.createElement('li'), b=document.createElement('button');
    b.innerHTML='<b>'+dd(i+1)+'</b>'+t.dataset.titulo;b.dataset.cursor='Ir';b.dataset.i=i;
    b.addEventListener('click',e=>{e.stopPropagation();fecharSum();setTimeout(()=>ir(i),60);});
    li.appendChild(b);lista.appendChild(li);
  });
  function abrirSum(){sum.classList.add('aberto');}
  function fecharSum(){sum.classList.remove('aberto');}
  $$('[data-sumario]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();abrirSum();}));
  $('.fechar',sum).addEventListener('click',e=>{e.stopPropagation();fecharSum();});

  /* teclado, clique e toque */
  addEventListener('keydown',e=>{
    if(caixa.classList.contains('aberta')){if(e.key==='Escape')fecharCaixa();return;}
    if(sum.classList.contains('aberto')){if(e.key==='Escape')fecharSum();return;}
    if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();ir(atual+1);}
    else if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){e.preventDefault();ir(atual-1);}
    else if(e.key==='Home')ir(0);else if(e.key==='End')ir(total-1);
    else if(e.key==='m'||e.key==='M')sum.classList.contains('aberto')?fecharSum():abrirSum();
  });
  const INTERATIVO='.rola,a,button,input,.amplia,[data-cursor],#gantt,#sumario,.ct,model-viewer,.celular,.janela,.tela-s,.janela-c,.dentro li,.trilha-cap span';
  $('#wrap').addEventListener('click',e=>{
    if(e.target.closest(INTERATIVO))return;
    if(sum.classList.contains('aberto'))return;
    ir(e.clientX>innerWidth/2?atual+1:atual-1);
  });
  let x0=null,y0=null;
  addEventListener('touchstart',e=>{x0=e.touches[0].clientX;y0=e.touches[0].clientY;},{passive:true});
  addEventListener('touchend',e=>{
    if(x0===null)return;const dx=e.changedTouches[0].clientX-x0,dy=e.changedTouches[0].clientY-y0;
    if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)&&!e.target.closest('#gantt,model-viewer'))ir(dx<0?atual+1:atual-1);x0=null;
  });

  /* lightbox */
  const caixa=$('#caixa');
  function fecharCaixa(){caixa.classList.remove('aberta');}
  $$('[data-amplia]').forEach(el=>el.addEventListener('click',e=>{
    e.stopPropagation();$('#cxImg').src=el.dataset.amplia;$('#cxTxt').textContent=el.dataset.legenda||'';caixa.classList.add('aberta');
  }));
  caixa.addEventListener('click',e=>{if(e.target===caixa||e.target.closest('.fechar'))fecharCaixa();});

  /* ---------------------------------------------------------- cursor e luz */
  const cur=$('#cursor'),anel=$('#anel'),anelTxt=$('#anelTxt');
  let mx=innerWidth/2,my=innerHeight/2,ax=mx,ay=my;
  addEventListener('mousemove',e=>{
    document.body.classList.add('tem-mouse');mx=e.clientX;my=e.clientY;
    cur.style.transform='translate('+mx+'px,'+my+'px)';
    const alvo=e.target.closest('[data-cursor],a,button,.amplia');
    anel.classList.toggle('sobre',!!alvo);
    anelTxt.textContent=alvo?(alvo.dataset.cursor||'Ir'):'';
    const r=stage.getBoundingClientRect();
    stage.style.setProperty('--mx',((mx-r.left)/escalaAtual)+'px');stage.style.setProperty('--my',((my-r.top)/escalaAtual)+'px');
  },{passive:true});
  (function segue(){ax+=(mx-ax)*.2;ay+=(my-ay)*.2;anel.style.transform='translate('+ax+'px,'+ay+'px)';requestAnimationFrame(segue);})();
  addEventListener('mousedown',()=>document.body.classList.add('clicou'));
  addEventListener('mouseup',()=>document.body.classList.remove('clicou'));
  addEventListener('touchstart',()=>document.body.classList.remove('tem-mouse'),{passive:true});
  $('#verAssim').addEventListener('click',()=>document.body.classList.add('forcar'));

  /* ---------------------------------------------------------- 07 quatro frentes */
  (function(){
    if(!$('#freDados'))return;
    const dados=$('#freDados').content.querySelectorAll('i');
    $$('.s-fre .frente').forEach(b=>b.addEventListener('click',e=>{
      e.stopPropagation();const i=+b.dataset.f,d=dados[i];
      $$('.s-fre .frente').forEach(x=>x.classList.toggle('on',x===b));
      $('#freN').textContent='Frente 0'+(i+1);
      const box=$('#freBox');box.innerHTML='<h3></h3><p></p>';box.querySelector('h3').textContent=d.dataset.t;box.querySelector('p').textContent=d.textContent;
      box.classList.remove('troca');void box.offsetWidth;box.classList.add('troca');
    }));
  })();

  /* ---------------------------------------------------------- 22 riscos */
  (function(){
    $$('.s-ris .risco button').forEach(b=>b.addEventListener('click',e=>{
      e.stopPropagation();const r=b.parentElement,ab=r.classList.contains('aberto');
      $$('.s-ris .risco').forEach(x=>x.classList.remove('aberto'));if(!ab)r.classList.add('aberto');
    }));
  })();

  /* ---------------------------------------------------------- depoimento Alltak */
  (function(){
    const v=$('#vidDep');if(!v)return;const cel=v.closest('.celular'),pr=$('#progDep');
    const alterna=e=>{e.stopPropagation();if(v.paused){v.play();}else{v.pause();}};
    $('#playDep').addEventListener('click',alterna);
    v.addEventListener('click',alterna);
    v.addEventListener('play',()=>cel.classList.add('tocando'));
    v.addEventListener('pause',()=>cel.classList.remove('tocando'));
    v.addEventListener('ended',()=>{cel.classList.remove('tocando');v.load();});
    v.addEventListener('timeupdate',()=>{pr.style.width=(v.duration?v.currentTime/v.duration*100:0)+'%';});
    // a fila de vídeos troca o que toca no celular
    const vids=$$('#filaVid .vid');
    vids.forEach(b=>b.addEventListener('click',e=>{
      e.stopPropagation();vids.forEach(x=>x.classList.toggle('on',x===b));
      v.pause();v.poster=b.dataset.poster;v.src=b.dataset.src;pr.style.width='0';
      $('#durDep').textContent='Assistir · '+b.dataset.dur;v.play();
    }));
  })();

  /* ---------------------------------------------------------- capas de capítulo: trilha e itens levam à tela */
  (function(){
    const capas=telas.filter(t=>t.classList.contains('s-cap'));
    capas.forEach(c=>{
      const n=c.dataset.capitulo,i0=telas.indexOf(c);
      c.querySelectorAll('.trilha-cap span').forEach(s=>{
        s.classList.toggle('on',s.dataset.c===n);s.classList.toggle('feito',s.dataset.c<n);s.dataset.cursor='Ir';
        s.addEventListener('click',e=>{e.stopPropagation();const alvo=telas.findIndex(t=>(t.dataset.cap||'').startsWith('('+s.dataset.c+')'));if(alvo>=0)ir(alvo);});
      });
      c.querySelectorAll('.dentro li').forEach((li,k)=>{li.dataset.cursor='Ir';li.addEventListener('click',e=>{e.stopPropagation();ir(i0+1+k);});});
    });
  })();

  /* ---------------------------------------------------------- frentes: no PDF, as quatro de uma vez */
  (function(){
    const box=$('.s-fre .todas-f');if(!box)return;
    $('#freDados').content.querySelectorAll('i').forEach((d,k)=>{const el=document.createElement('div');el.innerHTML='<span>0'+(k+1)+'</span><b></b><p></p>';el.querySelector('b').textContent=d.dataset.t;el.querySelector('p').textContent=d.textContent;box.appendChild(el);});
  })();

  /* ---------------------------------------------------------- simulador do Ariuno */
  (function(){
    const lis=$$('#simPassos li'),imgs=$$('#simVista img'),url=$('#simUrl'),n=$('#simuN');
    if(!lis.length)return;
    let k=0;
    function mostra(i){
      k=(i+lis.length)%lis.length;
      lis.forEach((l,j)=>{l.classList.toggle('on',j===k);l.classList.toggle('feito',j<k);});
      const im=+lis[k].dataset.img;imgs.forEach((m,j)=>m.classList.toggle('on',j===im));
      url.textContent=imgs[im].dataset.url;n.textContent='Passo '+(k+1)+' de '+lis.length;
      $$('.s-simu .fases span').forEach(f=>f.classList.toggle('on',f.className.indexOf('f-'+lis[k].dataset.fase)>=0));
    }
    lis.forEach((l,i)=>l.querySelector('button').addEventListener('click',e=>{e.stopPropagation();mostra(i);}));
    $('#simAnt').addEventListener('click',e=>{e.stopPropagation();mostra(k-1);});
    $('#simProx').addEventListener('click',e=>{e.stopPropagation();mostra(k+1);});
    aoEntrar['s-simu']=()=>mostra(0);
    roteiro('s-simu',{itens:()=>lis.map(l=>l.querySelector('button')),texto:i=>lis[i].textContent,extra:1500});
  })();

  /* ---------------------------------------------------------- central da rede: módulos */
  (function(){
    const lis=$$('#modsCentral li'),imgs=$$('#vistaCentral img'),abrir=$('#abrirCentral');
    if(!lis.length)return;
    function mostra(i){lis.forEach((l,j)=>l.classList.toggle('on',j===i));imgs.forEach((m,j)=>m.classList.toggle('on',j===i));abrir.href='assets/rede/central.html?v='+lis[i].querySelector('button').dataset.v;}
    lis.forEach((l,i)=>l.querySelector('button').addEventListener('click',e=>{e.stopPropagation();mostra(i);}));
    aoEntrar['s-central']=()=>mostra(0);
    roteiro('s-central',{itens:()=>lis.map(l=>l.querySelector('button')),texto:i=>lis[i].textContent,extra:2500});
  })();

  /* ---------------------------------------------------------- 3D e AR nos cases */
  (function(){
    let carregou=false;
    function liga(mv,src,ios){mv.classList.add('carregando');mv.setAttribute('src',src);if(ios)mv.setAttribute('ios-src',ios);}
    $$('model-viewer').forEach(mv=>mv.addEventListener('load',()=>mv.classList.remove('carregando')));
    // o visualizador 3D só é baixado quando uma tela com modelo aparece (cases e AR ao vivo)
    function ligaModelos(t){
      if(!carregou){carregou=true;const sc=document.createElement('script');sc.type='module';sc.src='assets/vendor/model-viewer.min.js';document.head.appendChild(sc);}
      t.querySelectorAll('model-viewer').forEach(mv=>{if(modoPdf)mv.removeAttribute('auto-rotate');if(!mv.getAttribute('src'))liga(mv,mv.dataset.src,mv.dataset.ios);});
    }
    aoEntrar['s-cases']=ligaModelos;
    aoEntrar['s-arb']=ligaModelos;
    aoEntrar['s-art']=ligaModelos;
  })();

  /* ---------------------------------------------------------- painel do QR */
  (function(){
    const abas=$$('#qrAbas button'),vistas=$$('#qrVista>div');
    abas.forEach((b,k)=>b.addEventListener('click',e=>{e.stopPropagation();abas.forEach(x=>x.classList.toggle('on',x===b));vistas.forEach((v,j)=>v.classList.toggle('on',j===k));}));
    // cada vista desce devagar pela tela do painel quando ela é mais alta que a janela
    vistas.forEach(v=>v.classList.add('pan'));
  })();

  /* ---------------------------------------------------------- temporizador
     Os botões de cada tela abrem sozinhos, um de cada vez, com tempo para ler.
     O primeiro clique da pessoa dentro da tela para o temporizador até ela sair e voltar. */
  function roteiro(cls,cfg){(autos[cls]=autos[cls]||[]).push(cfg);}
  // PDF: tela com botões vira uma página por botão (fonte/gerar-pdf.mjs chama estas duas)
  const SO_UMA_PAGINA=['s-ris','s-perf'];
  const cfgPdf=()=>{const t=$('.tela.ativa');return SO_UMA_PAGINA.includes(t.classList[1])?null:[t,(autos[t.classList[1]]||[])[0]];};
  window.__pdfEstados=()=>{const r=cfgPdf();if(!r||!r[1])return 0;const n=r[1].itens(r[0]).length;return n>1?n:0;};
  window.__pdfEstado=k=>{const [t,c]=cfgPdf();c.itens(t)[k].click();};
  // tempo de leitura: 3 s mais 45 ms por letra, entre 4,5 e 12 s
  const leitura=txt=>Math.max(4500,Math.min(12000,3000+String(txt||'').replace(/\s+/g,' ').trim().length*45));
  function pararAutos(){autoAtivos.forEach(clearTimeout);autoAtivos=[];$$('.relogio-auto').forEach(r=>r.remove());}
  function iniciarAutos(t){
    if(modoPdf)return;
    (autos[t.classList[1]]||[]).forEach(cfg=>{
      if(cfg.semAuto)return;
      const itens=cfg.itens(),n=itens.length;if(!n)return;
      const ms=k=>cfg.ms?cfg.ms(k):leitura(cfg.texto?cfg.texto(k):itens[k].textContent)+(cfg.extra||0);
      let i=cfg.inicio?cfg.inicio():Math.max(0,itens.findIndex(x=>x.matches('.on,.aberto')||x.parentElement.classList.contains('aberto')));
      function relogio(k,dur){
        const alvo=itens[k];
        $$('.relogio-auto',t).forEach(r=>{if(r.parentElement&&itens.includes(r.parentElement))r.remove();});
        if(getComputedStyle(alvo).position==='static')alvo.style.position='relative';
        const r=document.createElement('i');r.className='relogio-auto';alvo.appendChild(r);
        r.style.transitionDuration=dur+'ms';void r.offsetWidth;r.classList.add('corre');
      }
      function passo(){
        if(i+1>=n&&cfg.laco===false){$$('.relogio-auto',t).forEach(r=>r.remove());return;}
        i=(i+1)%n;itens[i].click();
        if(i+1>=n&&cfg.laco===false)return;
        const d=ms(i);relogio(i,d);autoAtivos.push(setTimeout(passo,d));
      }
      if(i<0){autoAtivos.push(setTimeout(passo,cfg.primeiro||2500));return;}
      const d=ms(i);relogio(i,d);autoAtivos.push(setTimeout(passo,d));
    });
  }
  // clique de verdade da pessoa (não o do temporizador) dentro da tela para tudo
  stage.addEventListener('pointerdown',e=>{if(e.isTrusted&&e.target.closest('.tela.ativa'))pararAutos();},true);

  const textoDe=id=>k=>$(id).content.querySelectorAll('i')[k].textContent;
  roteiro('s-fre',{itens:()=>$$('.s-fre .frente'),texto:textoDe('#freDados')});
  roteiro('s-qr',{itens:()=>$$('#qrAbas button'),ms:()=>8000});
  roteiro('s-ris',{itens:()=>$$('.s-ris .risco button'),texto:k=>$$('.s-ris .risco')[k].textContent});

  /* ---------------------------------------------------------- telas novas do grupo Bombril: abas genéricas */
  function abas(cls,cfg){
    cfg=cfg||{};
    const t=$('.'+cls);if(!t)return;
    const bts=$$('[data-aba]',t),pns=$$('[data-painel]',t);
    const mostra=k=>{bts.forEach((b,j)=>b.classList.toggle('on',j===k));pns.forEach((p,j)=>p.classList.toggle('on',j===k));if(cfg.aoMudar)cfg.aoMudar(k,t);};
    bts.forEach((b,k)=>b.addEventListener('click',e=>{e.stopPropagation();mostra(k);}));
    mostra(0);
    roteiro(cls,{itens:()=>bts,texto:k=>pns[k]?pns[k].textContent:'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',extra:cfg.extra||1000});
  }
  abas('s-design');abas('s-cota');abas('s-lead');abas('s-fol');abas('s-mont');
  ['s-p0','s-p1','s-p2','s-p3','s-p4','s-p5','s-p6'].forEach(c=>abas(c,{extra:4000}));
  abas('s-core',{extra:2500});const p2=(k,t)=>$$('[data-p2]',t).forEach(p=>p.classList.toggle('on',+p.dataset.p2===k));abas('s-cen',{extra:2500,aoMudar:p2});abas('s-can',{extra:5000,aoMudar:p2});abas('s-pol',{extra:3000});
  abas('s-cex',{aoMudar:(k,t)=>$$('.pin13',t).forEach((p,j)=>p.classList.toggle('on',j===k))});
  abas('s-13',{aoMudar:(k,t)=>$$('.pin13',t).forEach((p,j)=>p.classList.toggle('on',j===k))});
  abas('s-mapa',{extra:2500,aoMudar:(k,t)=>{$$('[data-zona]',t).forEach(z=>z.classList.toggle('on',k===0||+z.dataset.zona===k-1));$('.palco-m',t).classList.toggle('todas',k===0);}});

  /* vitrine por marca: cada peça abre a página de produto por cima da grade (05/11, noite) */
  $$('.s-vit').forEach(t=>{
    const cards=$$('[data-peca]',t),pags=$$('.vit-pag',t),grade=$('.vit-grade-bt',t);
    const fechar=()=>{pags.forEach(p=>p.classList.remove('on'));cards.forEach(c=>c.classList.remove('on'));t.classList.remove('com-pag');};
    cards.forEach((c,k)=>c.addEventListener('click',e=>{e.stopPropagation();fechar();pags[k].classList.add('on');c.classList.add('on');t.classList.add('com-pag');}));
    $$('.vit-x',t).forEach(x=>x.addEventListener('click',e=>{e.stopPropagation();fechar();}));
    grade.addEventListener('click',fechar);
    addEventListener('keydown',e=>{if(e.key==='Escape'&&t.classList.contains('com-pag')){e.stopPropagation();fechar();}},true);
    roteiro(t.classList[1],{itens:()=>[grade,...cards],semAuto:true});
  });
  abas('s-cn',{extra:2500,aoMudar:(k,t)=>{const L='AHSPC'[k];$$('.cn-p',t).forEach(f=>{const d=f.dataset.canais.includes(L);f.classList.toggle('dentro',d);f.classList.toggle('fora',!d);});$$('[data-painel].on [data-conta]',t).forEach(contar);}});

  /* simulador de investimento: escala P, M ou G carrega as quantidades; cada peça ajusta à mão (06/11) */
  $$('.s-sm').forEach(t=>{
    const L=$$('.sm-l',t),nf=new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0}),fmt=v=>'R$ '+nf.format(v);
    const soma=()=>{let tot=0,n=0;L.forEach(l=>{const q=Math.max(0,+$('input',l).value||0),s=q*+l.dataset.pu;$('.sm-sub',l).textContent=q?fmt(s):'fora';l.classList.toggle('zero',!q);tot+=s;n+=q;});$('#smTotal',t).textContent=fmt(tot);$('#smPecas',t).textContent=nf.format(n);};
    L.forEach(l=>{const i=$('input',l);
      $('.sm-menos',l).addEventListener('click',e=>{e.stopPropagation();i.value=Math.max(0,(+i.value||0)-5);soma();});
      $('.sm-mais',l).addEventListener('click',e=>{e.stopPropagation();i.value=(+i.value||0)+5;soma();});
      i.addEventListener('input',soma);['click','keydown','pointerdown'].forEach(ev=>i.addEventListener(ev,e=>e.stopPropagation()));});
    abas('s-sm',{extra:3000,aoMudar:k=>{const e='pmg'[k];L.forEach(l=>{$('input',l).value=l.dataset[e];});soma();}});
    const bm=$('[data-esc="M"]',t);if(bm)bm.click();
  });
  /* ClickLab: as duas janelas rolam juntas e os botões levam ao ponto da página */
  (function(){
    const t=$('.s-click2');if(!t)return;const rs=$$('[data-sync]',t);let trava=false;
    const max=r=>Math.max(1,r.scrollHeight-r.clientHeight);
    const ir=(k)=>{trava=true;rs.forEach(r=>{r.scrollTop=k?max(r)*.9:0;});requestAnimationFrame(()=>requestAnimationFrame(()=>trava=false));};
    rs.forEach(r=>{r.addEventListener('scroll',()=>{if(trava)return;trava=true;const f=r.scrollTop/max(r);rs.forEach(o=>{if(o!==r)o.scrollTop=f*max(o);});requestAnimationFrame(()=>requestAnimationFrame(()=>trava=false));},{passive:true});r.addEventListener('wheel',e=>e.stopPropagation(),{passive:true});});
    abas('s-click2',{extra:6000,aoMudar:(k)=>ir(k)});
    aoEntrar['s-click2']=()=>{$$('img',t).forEach(i=>i.decode&&i.decode().catch(()=>{}));setTimeout(()=>ir(0),60);};
  })();
  abas('s-zonas',{aoMudar:(k,t)=>$$('.planta [data-z]',t).forEach(z=>z.classList.toggle('on',+z.dataset.z===k))});
  /* loja perfeita: cada critério soma na nota */
  (function(){
    const cs=$$('.s-perf .crit'),N=$('#perfN'),B=$('#perfB'),T=$('#perfT');if(!cs.length)return;
    function conta(){const v=cs.filter(c=>c.classList.contains('on')).reduce((a,c)=>a+ +c.dataset.p,0);N.textContent=v;B.style.width=v+'%';
      T.textContent=v===0?'Comece marcando o que está certo na loja':v<60?'Loja abaixo da régua: abre plano de ação':v<85?'Loja boa: faltam pontos para ser perfeita':v<100?'Quase lá':'Loja perfeita';}
    cs.forEach(c=>c.addEventListener('click',e=>{e.stopPropagation();c.classList.toggle('on');conta();}));
    if(modoPdf)cs.forEach(c=>c.classList.add('on'));
    conta();
    roteiro('s-perf',{itens:()=>cs,inicio:()=>-1,primeiro:1800,laco:false,ms:()=>1300});
    aoEntrar['s-perf']=()=>{if(!modoPdf){cs.forEach(c=>c.classList.remove('on'));conta();}};
  })();
  /* janelas embutidas: só carregam quando a tela aparece */
  ['s-inst','s-click'].forEach(k=>{aoEntrar[k]=t=>$$('iframe[data-src]',t).forEach(f=>{if(!f.getAttribute('src'))f.src=f.dataset.src;});});

  /* ---------------------------------------------------------- cubagem: veículo + peça */
  (function(){
    const t=$('.s-cub2');if(!t)return;
    const D=JSON.parse($('#cubDados').textContent);let v='carreta',c='BL01';
    const fm=x=>new Intl.NumberFormat('pt-BR').format(x);
    const bV=$$('#cubV button'),bC=$$('#cubC button'),mv=$('#cubMv');
    function mostra(){
      if(c==='MIX')v='carreta';
      bV.forEach(b=>b.classList.toggle('on',b.dataset.v===v));bC.forEach(b=>b.classList.toggle('on',b.dataset.c===c));
      const k=v+'/'+c,x=D.c[k],e=D.e[c],V=D.v[v],vazio=$('#cubVazio');
      const tem=x&&x.n>0;
      const src='assets/cad/'+(tem?v+'-'+c:v)+'.glb';
      if(mv.dataset.atual!==src){mv.dataset.atual=src;if(t.classList.contains('em3d'))mv.setAttribute('src',src);}
      $('#cubFoto').src='assets/veic/'+v+'.webp';$('#cubLado').src='assets/cad/lado-'+(tem?v+'-'+c:v)+'.svg';
      vazio.classList.toggle('on',!tem);vazio.textContent=tem?'':'Não cabe: a maior embalagem deste kit é maior que o baú da '+V.nome.toLowerCase();
      $('#cubPlanoImg').src=tem?'assets/cad/plano-'+v+'-'+c+'.svg':'assets/cad/plano-'+v+'.svg';
      $('#cubPlano').dataset.amplia=$('#cubPlanoImg').src;$('#cubPlano').dataset.legenda='Plano de carga · '+V.nome+' · '+D.nc[c];
      $('#cubN').textContent=tem?fm(x.n):'0';
      const lim=x&&x.lim==='peso'?'o peso':'a cubagem';
      if(c==='MIX'){
        $('#cubNl').textContent='kits de 7 peças, para a região SP Capital';
        $('#cubKp').innerHTML='<div><b>'+x.via+'</b><span>carretas para a região</span></div><div><b>'+fm(x.cx)+'</b><span>volumes</span></div><div><b>'+e.m3.toString().replace('.',',')+' m³</b><span>de carga</span></div><div><b>'+(x.kg/1000).toFixed(1).replace('.',',')+' t</b><span>somando tudo</span></div>';
        $('#cubEmbT').textContent='O que vai na carga · kits e volumes';
        $('#cubEmb').innerHTML='<table>'+e.reg.map(r=>'<tr><td>'+r[1]+'</td><td style="font-family:var(--corpo)">'+r[0]+'</td></tr>').join('')+'</table><p class="tot">A imagem mostra a 1ª carreta, com '+x.ocups[0]+'% do baú ocupado.</p>';
      }else{
        $('#cubNl').textContent=tem?'kits por viagem na '+V.nome.toLowerCase():'não cabe neste veículo';
        $('#cubKp').innerHTML=tem?('<div><b>'+x.ocup+'%</b><span>do baú ocupado; quem limita é '+lim+'</span></div><div><b>'+(x.kg/1000).toFixed(1).replace('.',',')+' t</b><span>de '+V.kg+' kg de carga útil</span></div><div><b>'+fm(x.cx)+'</b><span>volumes no baú</span></div><div><b>'+(x.tir?x.via:'·')+'</b><span>'+(x.tir?'viagens para '+fm(x.tir)+' kits':'tiragem a definir')+'</span></div>'):'<div><b>'+V.m3+' m³</b><span>baú de '+V.med+'</span></div>';
        $('#cubEmbT').textContent='Embalagem de um kit · mm';
        $('#cubEmb').innerHTML='<table>'+e.vols.map((r,i)=>'<tr><td>'+(i+1)+'</td><td>'+r.join(' × ')+'</td></tr>').join('')+'</table><p class="tot">'+e.vols.length+' volume'+(e.vols.length>1?'s':'')+', '+e.m3+' m³ e '+fm(e.kg)+' kg por kit</p>';
      }
      $('#cubArq').innerHTML=tem?('<a href="assets/cad/'+v+'-'+c+'.step" download data-cursor="Baixar">Baixar STEP</a><a href="assets/cad/'+v+'-'+c+'.dxf" download data-cursor="Baixar">Baixar DXF 3D</a>'):'';
    }
    bV.forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();v=b.dataset.v;if(c==='MIX')c='BL01';mostra();}));
    bC.forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();c=b.dataset.c;mostra();}));
    $('#cub3d').addEventListener('click',e=>{e.stopPropagation();const on=t.classList.toggle('em3d');$('#cub3d').textContent=on?'Ver a lateral':'Ver em 3D';if(on){carregaMV();mv.setAttribute('src',mv.dataset.atual);}});
    aoEntrar['s-cub2']=()=>{mostra();};
    roteiro('s-cub2',{itens:()=>[...bC,...bV.slice(1)],ms:()=>7000});
    mostra();
    function carregaMV(){if(!document.querySelector('script[src*="model-viewer"]')){const sc=document.createElement('script');sc.type='module';sc.src='assets/vendor/model-viewer.min.js';document.head.appendChild(sc);}}
  })();

  /* ---------------------------------------------------------- início */
  const h=parseInt(location.hash.slice(1),10);
  const n0=isNaN(h)?0:Math.max(0,Math.min(total-1,h-1));
  telas.forEach(t=>t.classList.remove('ativa'));atual=n0;telas[n0].classList.add('ativa');
  atual=n0===0?1:0;aplicar(n0); // força a primeira aplicação
  telas.forEach((t,i)=>{if(i!==n0)t.classList.remove('ativa');});
})();
