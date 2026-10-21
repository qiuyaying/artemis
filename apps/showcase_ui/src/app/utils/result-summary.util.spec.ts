import { buildResultSummary } from './result-summary.util';
import { StepBlock } from '../core/models/stream.model';
const block = (data: any, type: StepBlock['type'] = 'checker'): StepBlock => ({id: 'test', type, timestamp: '', data});
describe('Result summary', () => {
  it('does not infer pass from task completion or unlabelled prose', () => {
    const s = buildResultSummary([block({action_taken: {action: 'report_task_status', args: {status: 'completed', explanation: 'Everything works'}}}, 'step')]);
    expect(s.source).toBe('missing');
    expect(s.counts.passed).toBeNull();
  });
  it('extracts explicit report labels without claiming absent categories are zero', () => {
    const s = buildResultSummary([block({action_taken: {action: 'report_task_status', args: {explanation: '1. 启动：【通过】正常\n2. 通讯录：【未验证】未授权\n3. 网络：【待确认】待复核'}}}, 'step')]);
    expect(s.source).toBe('report');
    expect(s.counts).toEqual({passed: 1, failed: null, unchecked: 1, inconclusive: 1});
  });
  it('deduplicates retries using the newest verdict and excludes superseded checks', () => {
    const s = buildResultSummary([
      block({verdicts: [{item_text: 'Open app', status: 'failed'}]}),
      block({verdicts: [{item_text: 'Open app', status: 'passed', evidence: 'Visible'}]}),
      block({status: 'superseded', verdicts: [{item_text: 'Old check', status: 'failed'}]})
    ]);
    expect(s.items.length).toBe(1);
    expect(s.counts.passed).toBe(1);
    expect(s.counts.failed).toBe(0);
  });
  it('prefers authoritative outcome totals over report labels', () => {
    const s = buildResultSummary([
      block({phase: 'outcome', tests: {passed: 2, failed: 1, inconclusive: 3, unchecked: 4}}),
      block({action_taken: {action: 'report_task_status', args: {explanation: '1. All: [PASS]'}}}, 'step')
    ]);
    expect(s.source).toBe('checker');
    expect(s.counts).toEqual({passed: 2, failed: 1, inconclusive: 3, unchecked: 4});
  });
  it('preserves multiline qualifications from the original report', () => {
    const s = buildResultSummary([block({action_taken: {action: 'report_task_status', args: {explanation: '1. Navigation: [PASS]\n- Permission denied; contacts not verified'}}}, 'step')]);
    expect(s.items[0].evidence).toContain('contacts not verified');
  });
  it('does not mix reports from previous runs', () => {
    expect(buildResultSummary([]).items).toEqual([]);
  });
});
