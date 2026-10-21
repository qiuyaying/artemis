import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';
import { ZH_CN } from './zh-cn';

export type UiLanguage = 'zh-CN' | 'en';
const STORAGE_KEY = 'artemis_ui_language';

@Injectable({ providedIn: 'root' })
export class LocaleService {
  private document = inject(DOCUMENT);
  readonly language = signal<UiLanguage>(this.initialLanguage());

  constructor() { this.document.documentElement.lang = this.language(); }

  private initialLanguage(): UiLanguage {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'zh-CN' || saved === 'en') return saved;
    } catch { /* Storage may be unavailable in private browsing. */ }
    return typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
  }

  setLanguage(language: UiLanguage): void {
    this.language.set(language);
    this.document.documentElement.lang = language;
    try { localStorage.setItem(STORAGE_KEY, language); } catch { /* Keep the in-memory choice. */ }
  }

  translate(value: unknown): string {
    const text = value == null ? '' : String(value);
    if (this.language() === 'en') return text;
    const key = text.trim().replace(/\s+/g, ' ');
    if (ZH_CN[key]) return ZH_CN[key];
    const status = /^(WDA connection failed: )(.*)$/.exec(key);
    if (status) return 'WDA 连接失败：' + status[2];
    const python = /^Python ([\d.]+) Ready$/.exec(key);
    if (python) return 'Python ' + python[1] + ' 已就绪';
    const swipe = /^Swiping Screen \((RIGHT|LEFT|UP|DOWN)\)$/.exec(key);
    if (swipe) return '滑动屏幕（' + ({RIGHT: '向右', LEFT: '向左', UP: '向上', DOWN: '向下'}[swipe[1]]) + '）';
    return text;
  }

  taskGoal(goal: string): string {
    return this.language() === 'zh-CN'
      ? goal + '\n\n请优先使用简体中文撰写任务结果、笔记和计划；若任务明确要求其他语言，请遵循任务要求。保留应用名称、代码和技术标识原文。'
      : goal;
  }
}
