/** Synthetic examples only. No service data, storage, uploads, or business decisions. */
export type CaseId = 'missing' | 'expiry' | 'matched';
export type Verdict = 'fatal' | 'review' | 'pass';
export interface Citation {
  readonly file: string;
  readonly page: number | null;
  readonly section: string;
  readonly quote: string;
}
export interface DemoCase {
  readonly id: CaseId;
  readonly title: string;
  readonly category: string;
  readonly label: string;
  readonly verdict: Verdict;
  readonly tender: Citation;
  readonly evidence: Citation;
  readonly canConfirm: boolean;
  readonly explanation: string;
}
export interface DemoState {
  selected: CaseId;
  confirmed: boolean;
  doubtful: Record<CaseId, boolean>;
  notes: Record<CaseId, string>;
  editorOpen: boolean;
}
export const CASE_ORDER: readonly CaseId[] = ['missing', 'expiry', 'matched'];
export const CASES: Readonly<Record<CaseId, DemoCase>> = {
  missing: {
    id: 'missing', title: '无重大违法记录声明', category: '资格声明 · 一票否决条款',
    label: '废标风险', verdict: 'fatal', canConfirm: false,
    tender: { file: '示例招标文件.pdf', page: 12, section: '第二章 · 供应商资格要求', quote: '投标人须提供近三年内无重大违法记录的书面声明，由法定代表人签署并加盖单位公章。未按要求提供的，按无效投标处理。' },
    evidence: { file: '示例企业资质包', page: null, section: '未定位到对应声明', quote: '已上传材料中，没有可定位到页码的对应声明。请补充签署并盖章后的文件，再重新核对。' },
    explanation: '缺少可定位证据，本项保持待处理。',
  },
  expiry: {
    id: 'expiry', title: '信息安全管理体系认证有效期', category: '资质证书 · 时效性核验',
    label: '待复核', verdict: 'review', canConfirm: false,
    tender: { file: '示例招标文件.pdf', page: 18, section: '第三章 · 资质与有效期要求', quote: '投标人须提供有效的信息安全管理体系认证证书，且证书在本项目投标截止日（2026年10月15日）仍处于有效期内。' },
    evidence: { file: '示例企业资质包.pdf', page: 8, section: '认证证书 · 有效期限', quote: '信息安全管理体系认证证书。证书有效期：2023年10月01日至2026年09月30日。最新换证材料尚未提供。' },
    explanation: '已有页码引用，但证书有效期早于截标日；需补充有效材料，不能直接通过。',
  },
  matched: {
    id: 'matched', title: '有效营业执照', category: '主体资格 · 双向引用已定位',
    label: '待人工确认', verdict: 'review', canConfirm: true,
    tender: { file: '示例招标文件.pdf', page: 9, section: '第二章 · 主体资格要求', quote: '供应商应具有独立承担民事责任的能力，须提供有效的营业执照复印件，并确保投标主体名称与营业执照载明名称一致。' },
    evidence: { file: '示例企业资质包.pdf', page: 3, section: '营业执照 · 示例信息', quote: '名称：示例科技有限公司。类型：有限责任公司。成立日期：2018年06月12日。营业期限：长期。示例投标主体：示例科技有限公司。' },
    explanation: '招标要求与企业证据均已定位。核对主体名称与有效性后，可以体验人工确认。',
  },
};
export function isCaseId(value: unknown): value is CaseId {
  return typeof value === 'string' && CASE_ORDER.some((id) => id === value);
}
export function initialState(): DemoState {
  return { selected: 'missing', confirmed: false, doubtful: { missing: false, expiry: false, matched: false }, notes: { missing: '', expiry: '', matched: '' }, editorOpen: false };
}
export function confirm(state: DemoState): boolean {
  const item = CASES[state.selected];
  if (!item.canConfirm || !item.tender.page || !item.evidence.page || state.confirmed) return false;
  state.confirmed = true;
  state.doubtful.matched = false;
  return true;
}
export function saveNote(state: DemoState, value: string): void {
  state.notes[state.selected] = value.slice(0, 500);
}
