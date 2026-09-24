/** An illustrative, local-only timeline. Durations are not scan performance claims. */
export type DemoPhase = 'ready' | 'running' | 'complete';
export interface DemoFrame {
  readonly afterMs: number;
  readonly message: string;
}
export const DEMO_FRAMES: readonly DemoFrame[] = Object.freeze([
  { afterMs: 0, message: '正在读取示例招标要求…' },
  { afterMs: 800, message: '正在对照示例企业材料…' },
  { afterMs: 1600, message: '正在整理待补和待复核事项…' },
]);
export const DEMO_DURATION_MS = 2400;
export const COMPLETE_MESSAGE = '示例检查完成：1 项待补，2 项待复核。';
