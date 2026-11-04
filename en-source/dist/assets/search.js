(function(){var q=document.getElementById('q'),out=document.getElementById('res'),idx=[];
function run(){var t=q.value.trim().toLowerCase();if(!t){out.innerHTML='';return}var w=t.split(/\s+/);
var r=idx.map(function(p){var s=0,h=(p.t+' '+p.d).toLowerCase();w.forEach(function(x){if(p.t.toLowerCase().indexOf(x)>-1)s+=3;if(h.indexOf(x)>-1)s+=1});return[s,p]}).filter(function(a){return a[0]>0}).sort(function(a,b){return b[0]-a[0]}).slice(0,20);
out.innerHTML=r.length?r.map(function(a){return'<a class="card" href="'+a[1].u+'"><h3>'+a[1].t.replace(/</g,'&lt;')+'</h3><p>'+a[1].d.replace(/</g,'&lt;')+'</p></a>'}).join(''):'<p>No results.</p>'}
fetch('/search-index.json').then(function(r){return r.json()}).then(function(j){idx=j;var p=new URLSearchParams(location.search).get('q');if(p){q.value=p;run()}});
q.addEventListener('input',run)})();