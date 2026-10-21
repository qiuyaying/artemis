import { StepBlock } from '../core/models/stream.model';
import { getReportStatusExplanation, isReportStatusAction } from './action-formatter.util';

export type VerdictCategory = 'passed' | 'failed' | 'inconclusive' | 'unchecked';
export interface ResultItem { category: VerdictCategory; text: string; evidence: string; }
export interface ResultSummary {
  source: 'checker' | 'report' | 'missing';
  counts: Record<VerdictCategory, number | null>;
  items: ResultItem[];
}
const categories: VerdictCategory[] = ['passed', 'failed', 'inconclusive', 'unchecked'];
const emptyCounts = (): ResultSummary['counts'] => ({passed: null, failed: null, inconclusive: null, unchecked: null});

/** Summarize recorded verdicts; completion alone is never evidence of a pass. */
export function buildResultSummary(blocks: StepBlock[]): ResultSummary {
  const items = new Map<string, ResultItem>();
  let outcome: any;
  let report = '';
  for (const block of blocks) {
    const d = block.data || {};
    if (block.type === 'checker') {
      if (d.phase === 'outcome' && d.tests) outcome = d.tests;
      if (d.isCompleted === false || ['superseded', 'error'].includes(d.status)) continue;
      for (const v of d.verdicts || []) {
        if (!categories.includes(v.status) || !v.item_text) continue;
        // Newer attempts replace earlier verdicts for the same check, including failures.
        items.set(String(v.item_text), {category: v.status, text: v.item_text, evidence: v.evidence || ''});
      }
      if (d.status === 'unchecked') {
        for (const item of d.items || []) {
          if (item.text) items.set(item.text, {category: 'unchecked', text: item.text, evidence: ''});
        }
      }
    }
    const actions = [d.action_taken, ...(Array.isArray(d.generic_tools) ? d.generic_tools : [])].flat();
    for (const action of actions) {
      if (isReportStatusAction(action)) report = getReportStatusExplanation(action);
    }
  }
  if (items.size || outcome) {
    const counts = emptyCounts();
    for (const category of categories) {
      const count = outcome?.[category];
      counts[category] = typeof count === 'number' && Number.isInteger(count) && count >= 0
        ? count : (items.size ? [...items.values()].filter(i => i.category === category).length : null);
    }
    return {source: 'checker', counts, items: [...items.values()]};
  }
  // Only explicit, per-item status tags are extracted. Prose is never guessed as a verdict.
  const labels: Record<string, VerdictCategory> = {
    '通过': 'passed', 'PASS': 'passed', '失败': 'failed', 'FAIL': 'failed',
    '待确认': 'inconclusive', 'INCONCLUSIVE': 'inconclusive',
    '未测试': 'unchecked', '未验证': 'unchecked', 'NOT TESTED': 'unchecked', 'UNCHECKED': 'unchecked'
  };
  const counts = emptyCounts();
  let previous: ResultItem | undefined;
  for (const line of report.split('\n')) {
    const match = /^\s*(?:[-*]|\d+[.、)])?\s*(.*?)\s*[【\[](通过|失败|待确认|未测试|未验证|PASS|FAIL|INCONCLUSIVE|NOT TESTED|UNCHECKED)[】\]]\s*(.*)$/i.exec(line);
    if (!match) {
      if (previous && line.trim()) previous.evidence += (previous.evidence ? '\n' : '') + line.trim();
      continue;
    }
    const category = labels[match[2].toUpperCase()];
    const text = match[1].replace(/[：:]\s*$/, '').trim();
    const evidence = match[3].trim();
    if (!text && !evidence) continue;
    const key = text || evidence;
    previous = {category, text: key, evidence: text ? evidence : ''};
    items.set(key, previous);
  }
  for (const item of items.values()) counts[item.category] = (counts[item.category] ?? 0) + 1;
  return {source: items.size ? 'report' : 'missing', counts, items: [...items.values()]};
}
