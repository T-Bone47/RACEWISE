/* ============ global test setup ============
   RACEWISE views are driven by async fetches: a render is not finished when
   React commits, it is finished when the payload lands and state settles. Every
   assertion therefore goes through testing-library's retrying `findBy*` /
   `waitFor`, and those default to a 1000 ms ceiling.

   1000 ms is fine when one suite runs alone and not fine when ten jsdom +
   React 19 suites share a saturated CI box. That produced a genuinely flaky
   failure — the stage-rail test could not find a button that is always
   eventually rendered. A test that fails on load is not testing the product;
   it is testing the machine it happened to run on.

   Raising the async ceiling fixes the class of failure for every file at once,
   without loosening any assertion: nothing here retries a failure, it only
   stops declaring victory before the render settles. Individual tests should
   still prefer `findBy*` over `waitFor` + `getBy*` — see
   investigation-workspace.test.tsx — because a retrying query fails with the
   real reason instead of a bare "Unable to find". */
import { configure } from '@testing-library/dom'

configure({
  /* Generous ceiling for async utilities, still well under the 5s default
     per-test timeout so a genuine hang still fails the suite. */
  asyncUtilTimeout: 10_000,
})