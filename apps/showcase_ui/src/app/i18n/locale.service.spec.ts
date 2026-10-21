import { TestBed } from '@angular/core/testing';
import { LocaleService } from './locale.service';

describe('LocaleService', () => {
  let saved: string | null;
  beforeEach(() => {
    saved = localStorage.getItem('artemis_ui_language');
    localStorage.setItem('artemis_ui_language', 'en');
    TestBed.configureTestingModule({});
  });
  afterEach(() => {
    if (saved === null) localStorage.removeItem('artemis_ui_language');
    else localStorage.setItem('artemis_ui_language', saved);
    document.documentElement.lang = 'en';
  });
  it('switches language, persists preference, and updates document language', () => {
    const locale = TestBed.inject(LocaleService);
    expect(locale.translate('Task Queue')).toBe('Task Queue');
    locale.setLanguage('zh-CN');
    expect(locale.translate('Task Queue')).toBe('任务队列');
    expect(document.documentElement.lang).toBe('zh-CN');
    expect(localStorage.getItem('artemis_ui_language')).toBe('zh-CN');
    TestBed.resetTestingModule();
    expect(TestBed.inject(LocaleService).language()).toBe('zh-CN');
  });
  it('preserves unknown content and technical identifiers', () => {
    const locale = TestBed.inject(LocaleService);
    locale.setLanguage('zh-CN');
    for (const value of ['com.apple.Preferences', '用户自己的笔记', 'My custom task']) {
      expect(locale.translate(value)).toBe(value);
    }
    expect(locale.translate(null)).toBe('');
  });
  it('adds Chinese output preference only to new Chinese-mode requests', () => {
    const locale = TestBed.inject(LocaleService);
    expect(locale.taskGoal('Open Settings')).toBe('Open Settings');
    locale.setLanguage('zh-CN');
    expect(locale.taskGoal('Open Settings')).toContain('请优先使用简体中文');
    expect(locale.taskGoal('Open Settings')).toContain('若任务明确要求其他语言');
    locale.setLanguage('en');
    expect(locale.taskGoal('Open Settings')).toBe('Open Settings');
  });
});
