/**
 * The RNVizion mark on /aiii/ renders in Montserrat 900.
 *
 * Why this exists: on 2026-09-28 a check of this page passed with no fonts loaded.
 * document.fonts.check() returns true for a face nobody declared, so its "true"
 * proved nothing. Each step below can fail on its own, for its own reason:
 *
 *   1. asks    the mark's computed style asks for Montserrat at weight 900
 *   2. loads   the page declares a Montserrat 900 face, and one finishes loading
 *   3. paints  Chrome reports the mark's glyphs were drawn with a downloaded Montserrat
 *
 * Break it on purpose before trusting it:
 *   npx checkly test -e SABOTAGE=1
 * That blocks the Google Fonts stylesheet, the condition the old check passed under:
 * no faces declared at all. Step 2 must fail.
 */
import { test, expect } from '@playwright/test'

const PAGE = 'https://rnvizion.dev/aiii/'
const MARK = 'nav a.logo'

test('mark renders in Montserrat 900 on /aiii/', async ({ page }) => {
  if (process.env.SABOTAGE === '1') {
    await page.route('https://fonts.googleapis.com/**', (route) => route.abort())
  }

  const response = await page.goto(PAGE)
  expect(response?.status(), `status of ${PAGE}`).toBe(200)
  const mark = page.locator(MARK)
  await expect(mark).toContainText('RNVizion')

  await test.step('1. the mark asks for Montserrat 900', async () => {
    const style = await mark.evaluate((el) => {
      const s = getComputedStyle(el)
      return { family: s.fontFamily, weight: s.fontWeight }
    })
    const first = style.family.split(',')[0].trim().replace(/^["']|["']$/g, '')
    expect(first, `font-family is ${style.family}`).toBe('Montserrat')
    expect(style.weight, 'font-weight').toBe('900')
  })

  await test.step('2. a Montserrat 900 face is declared and loads', async () => {
    const statuses = () =>
      page.evaluate(() =>
        [...document.fonts]
          .filter((f) => f.family.replace(/["']/g, '') === 'Montserrat' && f.weight === '900')
          .map((f) => f.status),
      )
    await expect
      .poll(statuses, { message: 'the page declares a Montserrat 900 face', timeout: 10_000 })
      .not.toEqual([])
    await expect
      .poll(statuses, { message: 'a Montserrat 900 face finished loading', timeout: 10_000 })
      .toContain('loaded')
  })

  await test.step('3. Chrome painted the mark with a downloaded Montserrat', async () => {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('DOM.enable')
    await cdp.send('CSS.enable')
    const { root } = await cdp.send('DOM.getDocument')
    const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: MARK })
    const { fonts } = await cdp.send('CSS.getPlatformFontsForNode', { nodeId })
    const painted = fonts.map((f) => `${f.familyName} (${f.isCustomFont ? 'downloaded' : 'system'})`)
    expect(fonts.length, 'fonts Chrome used for the mark').toBeGreaterThan(0)
    expect(
      fonts.every((f) => f.isCustomFont && /montserrat/i.test(f.familyName)),
      `fonts Chrome used for the mark: ${painted.join(', ')}`,
    ).toBe(true)
  })
})
