import { html } from '../util.js';
import { card, callout } from '../components.js';

export const meta = { path: 'about', title: 'Methodology & About', nav: 'Methodology & About' };

export async function load() { return {}; }

export function view() {
  return html`
  <div class="about-page">
    <p class="lead">PLAYBOOK 27 is a data-driven cricket analytics platform designed to evaluate player performance under high-pressure match situations. It combines contextual performance modelling, empirical-Bayes reliability estimation, predictive analytics and statistical validation to identify batters and bowlers with the strongest pressure-performance profiles.</p>
    <p class="lead" style="margin-bottom: 2rem;">The objective is not simply to identify players with impressive statistics, but to understand how reliably they perform when match situations become consequential.</p>

    ${callout('warn', 'The most important limitation', 'Pressure-specific performance is only weakly persistent across matches in this dataset. The rankings are genuine outputs of a predefined statistical methodology, but they carry substantial uncertainty and should not be interpreted as a precise prediction of future performance. The clutch delta — the difference between a player\'s pressure performance and their own baseline — showed no detectable signal in this dataset. Consequently, it receives zero weight in the final composite index.')}

    ${card('01. Defining pressure', html`<p>Pressure is contextual, not determined by overs alone.</p>
      <p>A win-probability model estimates the expected change in the batting team\'s probability of winning associated with the next delivery. This measure is called the <strong>Leverage Index</strong>.</p>
      <p>The model uses information available before the delivery, including:</p>
      <ul class="plain">
        <li>Balls and wickets remaining.</li>
        <li>Current score or required scoring rate.</li>
        <li>Venue par score.</li>
        <li>Team strength.</li>
      </ul>
      <p>Deliveries in the top 20% of leverage within each innings are classified as high-pressure situations (High and Critical).</p>
      <p>This means an eighth-over collapse or a demanding powerplay chase can represent greater pressure than a routine delivery in the final overs. Death overs are not automatically classified as high pressure.</p>`)}

    ${card('02. Measuring performance', html`<p>Each delivery is evaluated against the expected performance of an average player in a comparable match situation. Player-agnostic, cross-fitted models estimate expected outcomes without using the player\'s identity as a predictive feature.</p>
      <p><strong>For batters:</strong> Runs scored above expected; dismissal avoidance under pressure.</p>
      <p><strong>For bowlers:</strong> Runs saved relative to expectation; wickets taken above expectation.</p>
      <p>Wicket outcomes are converted into run-equivalent value using a base value of <strong>15.6 runs</strong>. The estimated value differs by innings: 25.7 runs in the first innings and 5.5 runs in the second innings. Alternative wicket valuations at 0.5× and 2× are included in sensitivity testing.</p>`)}

    ${card('03. Pressure Reliability Index (PRI)', html`<p>The Pressure Reliability Index combines three performance dimensions:</p>
      <p style="font-size:1.25rem;font-weight:700;padding:16px;background:#FCE8F2;border-left:5px solid #EA1A85;border-radius:6px;color:#0A1F44;margin:1.5rem 0;">PRI = 50 + 10 × mean(z<sub>level</sub>, z<sub>delta</sub>, z<sub>consistency</sub>)</p>
      <p>Where:</p>
      <ul class="plain">
        <li><strong>Level:</strong> The player\'s average performance under pressure.</li>
        <li><strong>Delta:</strong> The difference between pressure performance and the player\'s own baseline.</li>
        <li><strong>Consistency:</strong> The reliability of performance across pressure situations.</li>
      </ul>
      <p>The component estimates are adjusted using empirical-Bayes shrinkage. This reduces the influence of unusually high or low results from players with limited observations by pulling uncertain estimates towards the population average.</p>
      <p>Components are standardised using their estimated true between-player spread (τ). When a component has no detectable true signal, its estimated spread is zero and it contributes no weight to the composite index. In this analysis, the estimated spread for delta was zero.</p>
      <p>The minimum sample requirements were derived from the data: <strong>Batters: 128 pressure deliveries</strong>; <strong>Bowlers: 126 pressure deliveries</strong>.</p>`)}

    ${card('04. Uncertainty & Ranking Stability', html`<p>A ranking is only useful when its uncertainty is understood. PLAYBOOK 27 uses match-level bootstrapping to estimate: 90% uncertainty intervals and the probability of a player appearing in the top 10.</p>
      <p>Resampling matches, rather than individual deliveries, helps preserve the relationship between deliveries occurring within the same match.</p>
      <p>A 255-configuration sensitivity analysis evaluates how rankings respond to alternative assumptions involving: pressure thresholds and definitions, wicket valuation, component weights, and minimum sample requirements.</p>
      <p>Players are grouped into three interpretation tiers:</p>
      <ul class="plain">
        <li><strong>Tier A — Robust contender:</strong> Stronger support across alternative analytical assumptions.</li>
        <li><strong>Tier B — Assumption-sensitive:</strong> Ranking is more dependent on modelling choices.</li>
        <li><strong>Tier C — Ranked pool:</strong> Included in the evaluated pool, but with less robust support.</li>
      </ul>`)}

    ${card('05. Validation results — Split-half reliability', html`<p>The dataset is divided into two random match subsets to examine whether player rankings remain consistent across independent portions of the data. The table reports Spearman-Brown-corrected split-half reliability.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Measure</th><th class="num">Batters</th><th class="num">Bowlers</th></tr></thead>
        <tbody>
          <tr><td>Level (shrunk)</td><td class="num">0.29</td><td class="num">0.24</td></tr>
          <tr><td>Consistency (shrunk)</td><td class="num">0.09</td><td class="num">0.18</td></tr>
          <tr><td>Delta (shrunk)</td><td class="num">-0.26</td><td class="num">-0.02</td></tr>
          <tr><td>Composite</td><td class="num">0.19</td><td class="num">0.18</td></tr>
        </tbody>
      </table></div>
      <p>A value of 1.0 represents identical ordering across the two halves. A value near zero indicates little ranking persistence. The composite results indicate weak stability for both groups.</p>`)}

    ${card('06. Validation results — Out-of-time', html`<p>A separate chronological evaluation examines whether earlier player rankings correspond to later pressure-performance results.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Group</th><th>Cutoff</th><th class="num">Players</th><th class="num">Rank correlation</th><th class="num">Early top 10 later value</th><th class="num">Pool</th></tr></thead>
        <tbody>
          <tr><td>Batters</td><td>2025-03-31</td><td class="num">60</td><td class="num">-0.15</td><td class="num">11.7</td><td class="num">16.4</td></tr>
          <tr><td>Batters</td><td>2025-07-31</td><td class="num">45</td><td class="num">-0.37</td><td class="num">-2.8</td><td class="num">17.7</td></tr>
          <tr><td>Bowlers</td><td>2025-07-31</td><td class="num">53</td><td class="num">0.26</td><td class="num">17.7</td><td class="num">5.5</td></tr>
        </tbody>
      </table></div>
      <p>The results are mixed. The later bowler evaluation shows a positive relationship, while the batter evaluations show negative relationships.</p>`)}

    ${card('07. Data processing & quality', html`<p>The analysis covers <strong>803 matches from 867 matches with available ball-by-ball data</strong>.</p>
      <p>Excluded matches: 29 DLS/interrupted matches, 22 single-innings matches, 13 truncated matches.</p>
      <p>Automated data validation recorded: 12 checks passed, 7 warnings, 0 failures. Warnings are documented rather than silently ignored.</p>
      <p>All predictive features are constructed using information available before the delivery being evaluated. Outcome-describing columns are excluded from predictive features to reduce target leakage.</p>`)}

    ${card('08. Modelling decisions & limitations', html`<ul class="plain">
        <li><strong>Player clustering:</strong> Not implemented because the available signal was too weak to justify meaningful player clusters.</li>
        <li><strong>SHAP explanations:</strong> SHAP was unavailable in the offline environment. Permutation importance and ablation analysis were used instead.</li>
        <li><strong>Full Bayesian credible intervals:</strong> Replaced with empirical-Bayes estimation and match-level bootstrap uncertainty intervals.</li>
        <li><strong>Role-based weights:</strong> Not introduced because the available data did not provide a defensible basis for assigning additional weights by player role.</li>
        <li><strong>Auction prices and player availability:</strong> Excluded because these variables were not available in the dataset.</li>
      </ul>`)}

    ${card('09. Technology & implementation', html`<p>The implemented system uses Flask (backend), SQLite (database), Scikit-learn gradient boosting (ML), Pandas/NumPy/SciPy (data processing), and dependency-free JavaScript with SVG-based visualisations (frontend).</p>
      <p>The original implementation plan specified FastAPI, PostgreSQL, XGBoost, SHAP and React/Vite. These were substituted because the required packages could not be installed in the offline development environment.</p>`)}

    ${card('About PLAYBOOK 27', html`<p>PLAYBOOK 27 is an independent analytics submission developed for the SupeRR Selector competition.</p>
      <p>Its purpose is to demonstrate how contextual statistics, statistical modelling and uncertainty-aware evaluation can be applied to cricket performance analysis.</p>
      <p><strong>PLAYBOOK 27 — THE SCIENCE BEHIND THE SELECTION.</strong></p>
      <p class="muted small">Independent analytics for the SupeRR Selector competition. Not affiliated with or endorsed by Rajasthan Royals. Only derived aggregates are served by the platform. Raw competition data is not exposed.</p>`)}
  </div>
  `;
}

