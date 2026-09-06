# Top-K region display

Top-K is a frontend display operation after all backend component processing. The backend still returns every retained region and every raw component. No model, probability map, threshold, mask, or post-processing rule changes when a user selects K.

`frontend/src/regionSelection.ts` owns the default (25), options (5, 10, 20, 25, 50, All filtered), ranking, and selection. Regions are filtered by the selected class first, then ranked across matching classes by their exact backend `mean_probability`, descending. The UI's rounded percentage is not used for sorting. Equal scores use the existing ID as a deterministic tie-breaker. Selection creates a new array and retains the existing region objects, IDs and coordinates. Fewer than K available regions returns all available regions; none are padded or invented.

Analysis → Lesion Detection contains compact class and Regions shown controls. Boxes, Coordinates, selected details, and the region cards share one selected array. Raw, post-processed, and currently displayed counts are distinct. The explicit “View all raw model regions” switch bypasses Top-K/class filtering and disables those controls while active. Turning raw mode off restores the selected K. Compare synchronizes the controls for both eyes while ranking each eye independently.

Annotation retains its full predicted mask and its own class visibility checkboxes. Detection's class setting does not alter those checkboxes or the mask. Heatmaps and grading also remain independent of Top-K.

Report has its own Regions shown selector, default Top 25. The main table states how many retained predicted regions are shown and the chosen K. Its appendix always contains all retained regions. The report uses the same exact-score ranking and IDs as Analysis. “All filtered” is an explicit option in the report; no raw components are substituted. Print styling allows the larger main table to span pages with repeated headers, while the full appendix begins on a new page.

The API's existing `displayed_region_count` means the count after backend post-processing, before frontend Top-K; the frontend labels it “retained after post-processing.” Current displayed count is computed from the selected cached array. No API request is necessary for K, class or view changes.

## Actual reference-image result

Image: `20170629163635747.jpg`, OS.

| Measure | Value |
| --- | ---: |
| Raw components | 116 |
| Retained after post-processing | 110 |
| Top-K | 25 |
| Currently displayed | 25 |
| Lowest displayed mean pixel probability | 0.874125415210221 |

Top 5/10/20/25/50 displayed exactly 5/10/20/25/50 regions. All filtered displayed 110. Selecting EX and Top 50 displayed the three available retained EX regions. Scores remain mean pixel probabilities, never clinical confidence or severity.

## Tests and files

`scripts/test-topk.ts` checks every option, exact score precision, deterministic ties, class-before-ranking, empty/undersupplied selections, unchanged input arrays, and stable object identity. `desktop/topk-checks.cjs`, invoked by the existing real two-eye Electron smoke harness, compares rendered IDs/order with independently ranked API regions for every K, checks Boxes/Coordinates equality, verifies the unchanged annotation source, raw and retained counts, and class undersupply. Report checks cover every principal K, selection wording, and the untruncated appendix. The parent harness counts exactly two analyze requests for two images and records no renderer errors; K changes trigger none.

New: `frontend/src/regionSelection.ts`, `frontend/src/components/TopKSelector.tsx`, `scripts/test-topk.ts`, `desktop/topk-checks.cjs`, this document.

Modified: frontend `api.ts`, `types.ts`, `index.css`, `RegionCounts.tsx`, `AnalysisVisualization.tsx`, `AnalysisScreen.tsx`, `CompareScreen.tsx`, `ReportScreen.tsx`; `desktop/visual-smoke.cjs`; README/status/inventory documentation. Backend inference and post-processing are unchanged.

```powershell
cd C:\Users\ADMIN\Music\retina-desktop\desktop-app
node frontend/node_modules/tsx/dist/cli.mjs scripts/test-topk.ts
npm.cmd --prefix frontend run lint
npm.cmd run build
$env:RETINA_SMOKE='1'
$env:RETINA_VISUAL_SMOKE='1'
npm.cmd run desktop
Remove-Item Env:RETINA_SMOKE, Env:RETINA_VISUAL_SMOKE
```

Evidence: `work/topk-test.json`, `work/visual-smoke.json`, analysis screenshots, and `work/postprocessing-report.pdf`. Existing open app windows retain their loaded version; close and restart using `scripts/start-desktop.ps1` to load this update. Nothing was pushed to GitHub.
