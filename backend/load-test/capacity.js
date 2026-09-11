import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { SharedArray } from 'k6/data';
import { Rate } from 'k6/metrics';

const base = __ENV.BASE_URL || 'http://127.0.0.1:18080';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base)) throw new Error('Refusing non-loopback target');
const tokens = new SharedArray('isolated users', () => JSON.parse(open(__ENV.TOKENS_FILE || './tokens.json')));
const levels = (__ENV.LEVELS || '10,25,50,100,200,350,500').split(',').map(Number);
const hold = Number(__ENV.HOLD_SECONDS || 40), ramp = Number(__ENV.RAMP_SECONDS || 5);
const timeout = __ENV.REQUEST_TIMEOUT || '10s';
const think = Number(__ENV.THINK_SECONDS || 4);
const mode = __ENV.MODE || 'mixed';
const stages = [{duration:'15s',target:10}];
const windows = []; let at=15;
for (const level of levels) {
  stages.push({duration:`${ramp}s`, target:level}, {duration:`${hold}s`, target:level});
  windows.push({level, start:at+ramp, end:at+ramp+hold}); at+=ramp+hold;
}
stages.push({duration:'5s',target:0});
export const options = {
  scenarios: {listeners:{executor:'ramping-vus',startVUs:0,stages,gracefulRampDown:'15s',gracefulStop:'15s'}},
  summaryTrendStats:['avg','med','p(90)','p(95)','p(99)','max'],
  thresholds: {backend_failures:['rate<0.01'],http_req_duration:['p(95)<1000']},
};
const failures = new Rate('backend_failures');
function phase() {
  const elapsed=exec.instance.currentTestRunDuration/1000;
  return String((windows.find(w=>elapsed>=w.start&&elapsed<w.end)||{}).level || 'ramp');
}
function send(method,path,body,endpoint,valid) {
  const tags={level:phase(),endpoint,mode};
  const response=http.request(method,base+path,body,{headers:{Authorization:`Bearer ${tokens[__VU-1]}`,'Content-Type':'application/json'},timeout,tags});
  let ok=false;
  try { ok=valid(response); } catch (_) { }
  check(response,{[endpoint+' contract']:()=>ok},tags); failures.add(!ok,tags);
  return response;
}
export default function() {
  if (!tokens[__VU-1]) throw new Error('Insufficient unique users');
  const cached=(__VU-1)*4+(__ITER%4)+1;
  const miss=mode==='cold' || (mode==='mixed' && (__ITER+__VU*17)%50===49);
  const n=miss ? 1000000+__VU*10000+__ITER : cached;
  const name='Load Song '+String(n).padStart(6,'0');
  send('GET',`/api/v1/songs/suggestions?query=${encodeURIComponent(name)}`,null,'search',r=>r.status===200&&r.json().length>0);
  sleep(0.2+Math.random()*0.3);
  const play=send('POST',`/api/v1/songs/play?songName=${encodeURIComponent(name)}`,null,'play',r=>r.status===200&&r.json().id>0);
  if (play.status===200 && (__ITER+__VU)%4===0) {
    send('POST',`/api/v1/songs/${play.json().id}/like`,null,'like',r=>r.status===200&&r.json().liked===true);
  }
  send('POST','/api/v1/telemetry/interactions',JSON.stringify({song_id:'load-'+String(n).padStart(6,'0'),interaction_type:'play',session_id:`load-${__VU}`,play_duration_sec:30,completion_rate:0.17,device_timestamp:Date.now()}),'telemetry',r=>r.status===202);
  if ((__ITER+__VU)%3===0) {
    send('GET','/api/v1/recommendations?n=20',null,'recommendations',r=>r.status===200&&r.json().length===20);
  }
  // An actively browsing listener, not a continuously listening 3-minute song session.
  sleep(think*(0.75+Math.random()*0.5));
}
export function handleSummary(data) {
  return {[__ENV.SUMMARY_FILE||'summary.json']:JSON.stringify({...data,capacity:{levels,hold,ramp,think,mode,windows,timeout}},null,2)};
}
