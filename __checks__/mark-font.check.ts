import { BrowserCheck } from 'checkly/constructs'

// The check is the Playwright code in mark-font.spec.ts. This file gives it a name;
// the schedule and location come from checkly.config.ts.
new BrowserCheck('mark-font-aiii', {
  name: 'Mark renders in Montserrat 900 on /aiii/',
  code: { entrypoint: './mark-font.spec.ts' },
  tags: ['rnvizion.dev', 'brand', 'fonts'],
})
