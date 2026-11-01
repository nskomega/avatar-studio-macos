"""Cooperative cooling at completed GPU steps; never SIGSTOP a Metal process."""
from pathlib import Path
import json, os, subprocess, threading, time
import mlx.core as mx
HERE = Path(__file__).resolve().parent
class ThermalGuard:
    def __init__(self):
        (HERE / 'work').mkdir(parents=True, exist_ok=True)
        self.binary = HERE / 'work/thermal-state'
        if not self.binary.exists():
            subprocess.run(['swiftc', str(HERE/'thermal_state.swift'), '-o', str(self.binary)], check=True)
        self.log = HERE / 'work' / f'thermals-{os.getpid()}.jsonl'
        self.latest = None
        self.error = None
        self.phase = 'starting'
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()
    def sample(self):
        try:
            with self.log.open('a', buffering=1) as handle:
                while not self.stop.is_set():
                    metrics = json.loads(subprocess.check_output(['macmon', 'pipe', '-s', '1', '-i', '500'], text=True, timeout=12))
                    state = int(subprocess.check_output([str(self.binary)], text=True, timeout=5))
                    cpu = float(metrics['temp']['cpu_temp_avg']); gpu = float(metrics['temp']['gpu_temp_avg'])
                    if not (0 < cpu < 125 and 0 < gpu < 125):
                        raise RuntimeError('Invalid temperature readings')
                    self.latest = {'time': metrics['timestamp'], 'cpu_c': cpu, 'gpu_c': gpu, 'thermal_state': state, 'phase': self.phase}
                    handle.write(json.dumps(self.latest)+'\n')
                    self.stop.wait(.5)
        except BaseException as exc:
            self.error = exc
    def checkpoint(self, label, minimum=5):
        mx.synchronize()
        self.phase = f'cooling:{label}'
        start = time.monotonic()
        while True:
            if self.error is not None:
                raise RuntimeError('Thermal monitoring failed; aborting render') from self.error
            latest = self.latest
            if latest and max(latest['cpu_c'], latest['gpu_c']) <= 60 and latest['thermal_state'] <= 1 and time.monotonic()-start >= minimum:
                print(f"COOL {label}: CPU {latest['cpu_c']:.1f}, GPU {latest['gpu_c']:.1f}, state {latest['thermal_state']}", flush=True)
                self.phase = f'running-after:{label}'
                return
            time.sleep(1)
    def close(self):
        self.stop.set()
        self.thread.join(timeout=15)
    def check_if_hot(self, label):
        if self.error is not None:
            raise RuntimeError('Thermal monitoring failed') from self.error
        if self.latest and (max(self.latest['cpu_c'], self.latest['gpu_c']) >= 65 or self.latest['thermal_state'] >= 2):
            self.checkpoint(label, minimum=3)
