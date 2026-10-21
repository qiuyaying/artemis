import { Pipe, PipeTransform, inject } from '@angular/core';
import { LocaleService } from './locale.service';

@Pipe({ name: 't', standalone: true, pure: false })
export class TranslatePipe implements PipeTransform {
  private locale = inject(LocaleService);
  transform(value: unknown): string { return this.locale.translate(value); }
}
