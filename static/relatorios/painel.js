(function () {
  'use strict';
  const root = document.getElementById('sa-bi-dashboard');
  if (!root) return;
  const instances = [];
  const numeric = value => value === null || (typeof value === 'number' && Number.isFinite(value));
  const units = {count: 'Quantidade', currency: 'R$', percent: '%', percentage_point: 'p.p.', days: 'dias', score: 'nota (1–5)', rate: 'OS / 100 unidades'};
  const modes = {bar: 'Barras', line: 'Linha', scatter: 'Pontos'};
  const query = new URLSearchParams(location.search);
  root.querySelectorAll('.sa-navigation a').forEach(link => {
    const url = new URL(link.href, location.href);
    ['inicio', 'fim'].forEach(key => { if (query.has(key)) url.searchParams.set(key, query.get(key)); });
    if (query.has('obra') && link.dataset.area !== 'pos_obra') url.searchParams.set('obra', query.get('obra'));
    link.href = url.toString();
  });
  function format(value, chart) {
    if (value === null) return '—';
    const number = new Intl.NumberFormat('pt-BR', {minimumFractionDigits: chart.precision, maximumFractionDigits: chart.precision}).format(value);
    return chart.unit === 'currency' ? 'R$ ' + number : number + (chart.unit === 'count' ? '' : ' ' + units[chart.unit]);
  }
  function validate(data) {
    const c = data.chart;
    if (!c || !modes[c.type] || !['horizontal', 'vertical'].includes(c.orientation) || !units[c.unit] || !Number.isInteger(c.precision) || c.precision < 0 || c.precision > 10 || !Array.isArray(c.allowed_types) || !c.allowed_types.includes(c.type) || c.allowed_types.some(type => !modes[type]) || !['source','asc','desc','chronological'].includes(c.sort) || typeof c.negative !== 'boolean' || !numeric(c.min) || !numeric(c.max)) return false;
    if (!Array.isArray(data.rows) || data.rows.some(row => !numeric(row.raw))) return false;
    if (data.series && (!Array.isArray(data.series) || data.series.some(series => !Array.isArray(series.values) || series.values.length !== data.rows.length || series.values.some(value => !numeric(value))))) return false;
    const values = data.series && data.series.length ? data.series.flatMap(series => series.values) : data.rows.map(row => row.raw);
    return values.every(value => value === null || ((c.negative || value >= 0) && (c.min === null || value >= c.min) && (c.max === null || value <= c.max)));
  }
  function options(entry) {
    const data = entry.data, c = data.chart;
    const style = getComputedStyle(root), color = name => style.getPropertyValue(name).trim();
    const horizontal = c.orientation === 'horizontal';
    const source = data.series && data.series.length ? data.series : [{name: data.title, values: data.rows.map(row => row.raw)}];
    const category = {type:'category', data:data.rows.map(row => row.label), inverse:horizontal, axisLabel:{color:color('--sa-muted'), fontSize:10, width:horizontal?135:90, overflow:'truncate', hideOverlap:false}, axisTick:{show:false}, axisLine:{lineStyle:{color:color('--sa-line')}}};
    const value = {type:'value', name:units[c.unit], nameLocation:horizontal?'middle':'end', nameGap:horizontal?28:15, nameTextStyle:{color:color('--sa-muted'), fontSize:10}, min:c.min === null ? undefined : c.min, max:c.max === null ? undefined : c.max, minInterval:c.unit === 'count' ? 1 : undefined, axisLabel:{color:color('--sa-muted'), fontSize:10}, splitLine:{lineStyle:{color:color('--sa-line')}}};
    return {
      color:[color('--sa-bar'),color('--sa-gold'),color('--sa-success')],
      backgroundColor:color('--sa-card'), animation:false,
      aria:{enabled:true,description:data.title+'. '+units[c.unit]+'. '+(data.caption || '')+'. Consulte a tabela para os valores.'},
      grid:{left:horizontal?8:12,right:25,top:source.length>1?65:35,bottom:45,containLabel:true},
      legend:{show:source.length>1,textStyle:{color:color('--sa-text')},top:0},
      tooltip:{trigger:'axis',renderMode:'richText',confine:true,formatter:params => {
        const items = Array.isArray(params) ? params : [params];
        const index = items[0] ? items[0].dataIndex : -1;
        if (index < 0) return '';
        return [data.rows[index].label].concat(source.map(series => series.name+': '+format(series.values[index],c))).join('\n');
      }},
      xAxis:horizontal?value:category,yAxis:horizontal?category:value,
      series:source.map((series,index) => ({name:series.name,type:entry.mode,data:series.values,barMaxWidth:22,symbol:index%2?'diamond':'circle',symbolSize:8,smooth:false,connectNulls:false,lineStyle:{type:index%2?'dashed':'solid'},emphasis:{focus:'series'},markLine:c.unit==='percentage_point'?{silent:true,symbol:'none',label:{show:false},data:[horizontal?{xAxis:0}:{yAxis:0}],lineStyle:{color:color('--sa-muted'),type:'solid'}}:undefined}))
    };
  }
  root.querySelectorAll('[data-panel-json]').forEach(panel => {
    const status = panel.querySelector('.sa-chart-status');
    if (!status) return;
    let data;
    try { data = JSON.parse(document.getElementById(panel.dataset.panelJson).textContent); }
    catch (_) { status.textContent = 'Gráfico indisponível. Consulte a tabela.'; return; }
    if (!validate(data)) { status.textContent = 'Dados ou escala inconsistentes. Consulte a tabela.'; console.warn('SAARI: contrato de gráfico inválido', panel.dataset.panelJson); return; }
    const values = data.series && data.series.length ? data.series.flatMap(series => series.values) : data.rows.map(row => row.raw);
    if (!values.some(value => value !== null)) { status.textContent = 'Sem observações válidas para o gráfico.'; return; }
    const tableView = panel.querySelector('[data-sa-view="table"]');
    const chartView = panel.querySelector('[data-sa-view="chart"]');
    const holder = panel.querySelector('.sa-chart');
    const toggle = panel.querySelector('.sa-toggle');
    const entry = {data,panel,holder,chartView,tableView,mode:data.chart.type,instance:null};
    panel.querySelectorAll('[data-sort]').forEach(button => button.addEventListener('click', () => {
      const th = button.closest('th'), ascending = th.getAttribute('aria-sort') !== 'ascending';
      panel.querySelectorAll('[aria-sort]').forEach(cell => cell.setAttribute('aria-sort','none'));
      th.setAttribute('aria-sort',ascending?'ascending':'descending');
      const body = tableView.querySelector('tbody');
      Array.from(body.rows).sort((a,b) => {
        const x=data.rows[Number(a.dataset.rowIndex)], y=data.rows[Number(b.dataset.rowIndex)];
        if (button.dataset.sort === 'label') return x.label.localeCompare(y.label,'pt-BR',{numeric:true})*(ascending?1:-1);
        if (x.raw === null) return y.raw === null ? 0 : 1;
        if (y.raw === null) return -1;
        return (x.raw-y.raw)*(ascending?1:-1);
      }).forEach(row => body.appendChild(row));
    }));
    function activate() {
      if (entry.instance) return;
      if (!window.echarts) { status.textContent='Gráfico indisponível. Tabela preservada.'; return; }
      try {
        chartView.hidden=false;
        holder.style.height = (data.chart.orientation==='horizontal'?Math.max(280,data.rows.length*30+85):300)+'px';
        entry.instance=window.echarts.init(holder,null,{renderer:'canvas'});
        entry.instance.setOption(options(entry));
        tableView.hidden=true; toggle.hidden=false; status.textContent='';
        const controls=panel.querySelector('.sa-chart-tools');
        data.chart.allowed_types.forEach(type => {
          const button=document.createElement('button'); button.type='button'; button.textContent=modes[type]; button.dataset.chartMode=type;
          button.setAttribute('aria-pressed',String(type===entry.mode));
          button.addEventListener('click',() => {entry.mode=type; entry.instance.setOption(options(entry),true); controls.querySelectorAll('[data-chart-mode]').forEach(item => item.setAttribute('aria-pressed',String(item===button)));});
          controls.insertBefore(button,controls.querySelector('[data-chart-download]'));
        });
        instances.push(entry);
      } catch (_) { if(entry.instance) entry.instance.dispose(); entry.instance=null; chartView.hidden=true; tableView.hidden=false; status.textContent='Gráfico indisponível. Tabela preservada.'; }
    }
    toggle.querySelectorAll('[data-sa-switch]').forEach(button => button.addEventListener('click',() => {
      const chart=button.dataset.saSwitch==='chart'; chartView.hidden=!chart; tableView.hidden=chart;
      toggle.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed',String(item===button)));
      if(chart && entry.instance) requestAnimationFrame(() => entry.instance.resize());
    }));
    panel.querySelector('[data-chart-download]').addEventListener('click',() => {
      if(!entry.instance) return;
      const anchor=document.createElement('a'); anchor.download='saari-'+panel.dataset.panelJson+'.png'; anchor.href=entry.instance.getDataURL({type:'png',pixelRatio:2,backgroundColor:getComputedStyle(root).getPropertyValue('--sa-card').trim()}); anchor.click();
    });
    activate();
  });
  const resize = () => instances.forEach(entry => {if(!entry.chartView.hidden) entry.instance.resize();});
  if(window.ResizeObserver) {const observer=new ResizeObserver(resize); observer.observe(root);} else window.addEventListener('resize',resize);
  new MutationObserver(() => instances.forEach(entry => entry.instance.setOption(options(entry),true))).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  const details = [];
  window.addEventListener('beforeprint',() => {root.querySelectorAll('details').forEach(item => {details.push([item,item.open]); item.open=true;});});
  window.addEventListener('afterprint',() => {details.splice(0).forEach(([item,open]) => {item.open=open;}); resize();});
})();

