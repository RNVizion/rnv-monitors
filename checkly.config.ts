import { defineConfig } from 'checkly'
import { Frequency } from 'checkly/constructs'

// Monitoring as code for rnvizion.dev. Checks live in __checks__.
export default defineConfig({
  projectName: 'RNV Monitors',
  logicalId: 'rnv-monitors',
  repoUrl: 'https://github.com/RNVizion/rnv-monitors',
  checks: {
    activated: true,
    muted: false,
    // Hourly from one location keeps this check inside the free plan's monthly browser runs.
    frequency: Frequency.EVERY_1H,
    locations: ['us-east-1'],
    tags: ['rnvizion.dev'],
    checkMatch: '**/__checks__/**/*.check.ts',
  },
  cli: {
    runLocation: 'us-east-1',
  },
})
