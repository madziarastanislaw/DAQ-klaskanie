// Runs the actual session/state-machine C++ functions with a fake monotonic clock.
// Windows host: MSVC (Visual Studio 2022). No Arduino/device needed.
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
const root = resolve(import.meta.dirname, '..');
const session = readFileSync(join(root, 'Klaskacz/session.h'), 'utf8');
const ino = readFileSync(join(root, 'Klaskacz/Klaskacz.ino'), 'utf8');
const audio = readFileSync(join(root, 'Klaskacz/audio.h'), 'utf8');
const config = readFileSync(join(root, 'Klaskacz/config.h'), 'utf8');
const define = name => config.match(new RegExp('^#define\\s+' + name + '\\s+(\\d+)', 'm'))[1];
const detectorStart = audio.indexOf('    uint32_t nowMs =');
const detectorEnd = audio.indexOf('    prevA = A;', detectorStart);
if (detectorStart < 0 || detectorEnd < 0) throw Error('Detector test extraction requires updating');
function fn(source, name) {
  const start = source.search(new RegExp('(?:void|bool|uint32_t) ' + name + '\\('));
  if (start < 0) throw Error(name);
  let end = source.indexOf('{', start), depth = 1, i = end + 1;
  while (depth) { if (source[i] === '{') depth++; if (source[i] === '}') depth--; i++; }
  return source.slice(start, i);
}
const dir = mkdtempSync(join(tmpdir(), 'clap-firmware-'));
const code = `
#include <cassert>
#include <cstdint>
#include <ctime>
#include <string>
#include <iostream>
#include <deque>
#include <functional>
using String = std::string;
#define MAX_CLAPS_RAM ${define('MAX_CLAPS_RAM')}
#define FLASH_BATCH ${define('FLASH_BATCH')}
#define BUZZER_GUARD_MS ${define('BUZZER_GUARD_MS')}
#define WARMUP_BLOCKS ${define('WARMUP_BLOCKS')}
#define REFRACTORY_MS ${define('REFRACTORY_MS')}
#define CLAP_FREQ_MIN_HZ ${define('CLAP_FREQ_MIN_HZ')}
#define CLAP_FREQ_MAX_HZ ${define('CLAP_FREQ_MAX_HZ')}
#define AUTO_STOP_MS ${define('AUTO_STOP_MS')}
#define PIN_BUZZER ${define('PIN_BUZZER')}
#define LOW 0
#define HIGH 1
#define pdTRUE 1
#define CLAP_QUEUE_SIZE ${config.match(/^#define\s+CLAP_QUEUE_SIZE[ \t]+([^\r\n]+)/m)[1]}
static_assert(CLAP_QUEUE_SIZE > 60000 / (REFRACTORY_MS + 1), "Full competition queue capacity");
enum SessionState { S_IDLE, S_ARMED, S_RUNNING, S_FINISHED };
enum Cmd { CMD_START_STOP, CMD_START, CMD_STOP, CMD_RESET };
struct ClapEvent { uint64_t t_us; uint16_t peak; };
${session.slice(session.indexOf('struct Clap {'), session.indexOf('const char* stateName'))}
uint64_t clockUs=1000000, ignoreUntilUs=0, armedAtUs=0;
uint32_t buzzerUntil=0, gBoot=1;
uint64_t processedUs=0;
int buzzerLevel=HIGH;
std::deque<ClapEvent> pendingClaps;
uint32_t millis(){return (uint32_t)(clockUs/1000);}
void digitalWrite(int pin,int level){assert(pin==PIN_BUZZER); buzzerLevel=level;}
int saves=0, opens=0, normalStarts=0;
Session persisted;
uint64_t esp_timer_get_time() {return clockUs;}
bool timeValid(){return false;}
uint32_t sessionNextId(){return S.id+1;}
void storageOpen(){opens++;}
void storageFlush(){S.flushed=S.count;}
void sessionSaveMeta(){persisted=S; saves++;}
${fn(ino,'beep')}
void xQueueReset(int){pendingClaps.clear();}
int clapQueue=0;
int xQueueReceive(int,ClapEvent* ev,int){
  if(pendingClaps.empty()) return 0;
  *ev=pendingClaps.front(); pendingClaps.pop_front(); return pdTRUE;
}
uint64_t audioProgress(){return processedUs;}
void pollButtons(){}
void serialCommands(){}
void drawDisplay(){}
bool wifiOn=false, dbgDetector=false;
float gBaseline=0; uint32_t gEffThr=0;
struct { void printf(const char*,...){} } Serial;
struct { std::function<void()> callback; void handleClient(){if(callback)callback();} } server;
struct StepDone{};
void vTaskDelay(int){throw StepDone{};}
void startMeasurement(){normalStarts++; S.state=S_ARMED;}
int detected=0; float gFreq=0; uint16_t gLastPeak=100;
float estimateFrequencyFFT(){return 1000;}
void xQueueSend(int,ClapEvent*,int){detected++;}
void audioBlock(float A, uint64_t t_us) {
  static uint32_t lastClapMs=0;
  static bool prevLoud=false;
  uint32_t blocks=100, thr=100;
  ${audio.slice(detectorStart, detectorEnd)}
}
${['sessionClear','sessionElapsedMs','sessionBegin','sessionFinish','sessionAddClap'].map(n=>fn(session,n)).join('\n')}
${['handleClap','sessionActive','startCompetition','competitionTick','handleCommand'].map(n=>fn(ino,n)).join('\n')}
${fn(ino,'logicTask')}
void logicStep(){try{logicTask(nullptr);}catch(const StepDone&){} }
void event(uint64_t t){handleClap({t,100});}
void prepare(){
  sessionClear(); clockUs=1000000; buzzerUntil=0;
  startCompetition("Ala",15);
  assert(S.state==S_ARMED);
  event(clockUs); assert(S.count==0);
  clockUs+=2999999; competitionTick(clockUs); assert(S.t0_us==0);
  clockUs++; competitionTick(clockUs); assert(S.t0_us==UINT64_MAX);
  event(clockUs); assert(S.count==0);
  clockUs+=300000; buzzerUntil=0; competitionTick(clockUs);
  assert(S.t0_us==clockUs+150000);
  event(S.t0_us-1); assert(S.count==0);
}
int main(){
  audioBlock(0,1000000); audioBlock(200,1016000); audioBlock(200,1020000);
  assert(detected==1);
  audioBlock(200,1100000); assert(detected==1); // One long sound is still one clap.
  audioBlock(0,1116000); audioBlock(200,1132000); assert(detected==2);
  audioBlock(0,1133000); audioBlock(200,1134000); assert(detected==2);
  audioBlock(0,1148000); audioBlock(200,1180000); assert(detected==3);
  std::cout<<"PASS sustained sound counted once, rapid separate claps and refractory period\\n";
  prepare();
  uint64_t start=S.t0_us,end=S.end_us;
  assert(end-start==15000000);
  // Queue can contain the first event before the logic changes ARMED to RUNNING.
  event(start); assert(S.count==1);
  clockUs=start; competitionTick(start); assert(S.state==S_RUNNING);
  event(start+51000); event(start+102000); assert(S.count==3);
  // Simulate a long Wi-Fi handler and an event whose FFT completes after deadline.
  clockUs=end+2000000; competitionTick(end-1); assert(S.state==S_RUNNING);
  assert(sessionElapsedMs()==15000);
  event(end-1); event(end); event(end+1); assert(S.count==4);
  competitionTick(end); assert(S.state==S_FINISHED && S.completed);
  assert(S.stop_us==end && saves==1 && persisted.count==4 && persisted.completed);
  event(end-1000); assert(S.count==4);
  std::cout<<"PASS exact 15s window, countdown, guard, delayed queue, Wi-Fi delay, persistence\\n";
  prepare(); clockUs=S.t0_us; competitionTick(clockUs); event(clockUs);
  clockUs+=1000000; handleCommand(CMD_START); assert(S.competition && S.count==1);
  handleCommand(CMD_STOP); assert(S.stopping); event(clockUs-1); event(clockUs);
  competitionTick(clockUs); assert(S.state==S_FINISHED && !persisted.completed && S.count==2);
  prepare(); handleCommand(CMD_RESET); competitionTick(clockUs);
  assert(S.state==S_IDLE && !persisted.completed && persisted.count==0);
  prepare(); clockUs=S.t0_us; competitionTick(clockUs); clockUs=S.end_us;
  handleCommand(CMD_STOP); competitionTick(clockUs); assert(S.completed);
  std::cout<<"PASS stop/reset, session exclusion, stop at deadline\\n";
  clockUs+=500000; sessionBegin(clockUs); event(clockUs); event(clockUs+500000);
  assert(!S.competition && S.count==2); clockUs+=1000000; handleCommand(CMD_STOP);
  assert(S.state==S_FINISHED && persisted.count==2);
  handleCommand(CMD_START); assert(normalStarts==1);
  std::cout<<"PASS ordinary measurement regression\\n";
  for (uint32_t seconds : {10,30,60}) {
    sessionClear(); buzzerUntil=0; startCompetition("Bob",seconds);
    clockUs=S.countdownEnd_us; competitionTick(clockUs);
    clockUs+=300000; buzzerUntil=0; competitionTick(clockUs);
    clockUs=S.t0_us; competitionTick(clockUs);
    for (uint64_t t=S.t0_us;t<S.end_us;t+=51000) event(t);
    uint32_t expected=S.count;
    clockUs=S.end_us; competitionTick(clockUs);
    assert(S.completed && sessionElapsedMs()==seconds*1000 && persisted.count==expected);
  }
  std::cout<<"PASS 10/30/60s trials at rapid detector rate\\n";
  sessionClear(); clockUs=1000000; buzzerUntil=0; buzzerLevel=HIGH;
  startCompetition("Loop",15);
  clockUs=3999999; logicStep(); assert(S.t0_us==0 && buzzerLevel==HIGH);
  clockUs=4000000; logicStep(); assert(S.t0_us==UINT64_MAX && buzzerLevel==LOW);
  clockUs=4300000; logicStep(); assert(buzzerLevel==HIGH && buzzerUntil==0);
  clockUs+=1000; logicStep(); assert(S.t0_us==clockUs+150000);
  clockUs=S.t0_us; processedUs=clockUs;
  pendingClaps.push_back({clockUs-1,100}); pendingClaps.push_back({clockUs,100});
  logicStep(); assert(S.state==S_RUNNING && S.count==1);
  uint64_t loopEnd=S.end_us;
  wifiOn=true; server.callback=[&]{clockUs=loopEnd+2000000;};
  logicStep(); server.callback=nullptr;
  assert(S.state==S_RUNNING);
  processedUs=loopEnd-1;
  pendingClaps.push_back({loopEnd-1,100}); pendingClaps.push_back({loopEnd,100});
  logicStep(); assert(S.state==S_RUNNING && S.count==2);
  processedUs=loopEnd; logicStep();
  assert(S.state==S_FINISHED && S.completed && S.stop_us==loopEnd && persisted.count==2);
  std::cout<<"PASS real logicTask, active-low buzzer, guard, HTTP delay and queue draining\\n";
}
`;
writeFileSync(join(dir, 'test.cpp'), code);
const vc = process.env.VSDEVCMD || 'C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\Common7\\Tools\\VsDevCmd.bat';
writeFileSync(join(dir, 'run.cmd'), `@echo off\r\ncall "${vc}" -arch=x64 >nul\r\nif errorlevel 1 exit /b 1\r\ncl /nologo /EHsc /std:c++17 test.cpp /Fe:test.exe\r\nif errorlevel 1 exit /b 1\r\ntest.exe\r\n`);
process.stdout.write(execFileSync('cmd.exe', ['/d', '/c', join(dir, 'run.cmd')], { cwd:dir, encoding:'utf8', windowsHide:true }));
