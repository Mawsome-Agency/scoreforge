/**
 * Data fetching and aggregation for test accuracy dashboard
 */

// Cached data
let allData = null;
let baselineData = null;
let iterationData = null;
let fixtureData = {};

/**
 * Fetch all data from result files
 * @returns {Promise<Object>} - Object with runs, baselines, and fixtures
 */
async function fetchAllResults() {
    if (allData) return allData;
    
    try {
        const [indexRes, iterationRes] = await Promise.all([
            fetch('../results/index.json'),
            fetch('../results/iteration_summary.json')
        ]);
        
        const indexData = await indexRes.json();
        const iterationResults = await iterationRes.json();
        
        // Fetch baseline results
        const baselineRes = await fetchBaselineResults();
        
        // Fetch per-fixture details
        await fetchFixtureDetails(indexData.runs);
        
        allData = {
            runs: indexData.runs || [],
            baselines: baselineRes || [],
            iterations: iterationResults || [],
            fixtures: fixtureData
        };
        
        return allData;
    } catch (error) {
        console.error('Error fetching results:', error);
        return { runs: [], baselines: [], iterations: [], fixtures: {} };
    }
}

/**
 * Fetch all baseline result files
 * @returns {Promise<Object[]>} - Array of baseline result objects
 */
async function fetchBaselineResults() {
    try {
        // Fetch the baseline directory listing
        const dirRes = await fetch('../results/baseline/');
        const dirText = await dirRes.text();
        
        // Parse directory listing to find timestamped directories
        const dirPattern = /href="(\d{8}_\d{6})\/"/g;
        const matches = [...dirText.matchAll(dirPattern)];
        const timestamps = matches.map(m => m[1]);
        
        // Sort by timestamp (newest first)
        timestamps.sort().reverse();
        
        // Fetch each baseline file (limit to 10 most recent)
        const baselines = [];
        for (const ts of timestamps.slice(0, 10)) {
            try {
                const res = await fetch(`../results/baseline/${ts}/baseline_results.json`);
                const data = await res.json();
                baselines.push({
                    ...data,
                    timestamp: data.summary?.timestamp || ts
                });
            } catch (e) {
                console.warn(`Failed to load baseline ${ts}:`, e);
            }
        }
        
        return baselines;
    } catch (error) {
        console.error('Error fetching baselines:', error);
        return [];
    }
}

/**
 * Fetch fixture details (summary.json files)
 * @param {Object[]} runs - Array of run entries from index.json
 */
async function fetchFixtureDetails(runs) {
    const fixtureNames = [...new Set(runs.map(r => r.fixture))];
    
    for (const fixture of fixtureNames) {
        try {
            // Get latest run directory for this fixture
            const fixtureRuns = runs.filter(r => r.fixture === fixture);
            if (fixtureRuns.length === 0) continue;
            
            const latestRun = fixtureRuns.sort((a, b) => 
                new Date(b.timestamp) - new Date(a.timestamp)
            )[0];
            
            // Try to fetch summary.json
            const res = await fetch(`../results/${fixture}/${latestRun.run_id}/summary.json`);
            if (res.ok) {
                fixtureData[fixture] = await res.json();
            }
        } catch (e) {
            console.warn(`Failed to fetch details for ${fixture}:`, e);
        }
    }
}

/**
 * Filter runs by date range
 * @param {Object[]} runs - Array of run entries
 * @param {string} startDate - ISO date string or 'YYYY-MM-DD'
 * @param {string} endDate - ISO date string or 'YYYY-MM-DD'
 * @returns {Object[]} - Filtered runs
 */
function filterByDate(runs, startDate, endDate) {
    if (!startDate && !endDate) return runs;
    
    const start = startDate ? new Date(startDate) : null;
    const end = endDate ? new Date(endDate) : null;
    
    return runs.filter(run => {
        const runDate = parseTimestamp(run.timestamp);
        if (start && runDate < start) return false;
        if (end && runDate > end) return false;
        return true;
    });
}

/**
 * Filter runs by fixture name pattern
 * @param {Object[]} runs - Array of run entries
 * @param {string} pattern - Search pattern (substring match)
 * @returns {Object[]} - Filtered runs
 */
function filterByFixture(runs, pattern) {
    if (!pattern) return runs;
    const lower = pattern.toLowerCase();
    return runs.filter(run => 
        run.fixture?.toLowerCase().includes(lower)
    );
}

/**
 * Filter by difficulty tier
 * @param {Object[]} runs - Array of run entries with baseline data
 * @param {string} tier - 'easy', 'medium', 'hard', or 'complex'
 * @returns {Object[]} - Filtered runs
 */
function filterByTier(runs, tier) {
    if (!tier) return runs;
    
    // Map tiers to baseline fixture difficulties
    const tierMap = {
        'easy': ['easy'],
        'medium': ['medium'],
        'hard': ['hard'],
        'complex': ['complex', 'orchestral', 'choral']
    };
    
    const validDifficulties = tierMap[tier] || [];
    
    return runs.filter(run => {
        const fixture = fixtureData[run.fixture];
        const difficulty = fixture?.difficulty;
        return validDifficulties.includes(difficulty);
    });
}

/**
 * Aggregate data by difficulty tier
 * @param {Object[]} runs - Array of run entries
 * @returns {Object} - Object with tier stats
 */
function aggregateByTier(runs) {
    const tiers = {
        easy: { count: 0, avgAccuracy: 0, fixtures: [] },
        medium: { count: 0, avgAccuracy: 0, fixtures: [] },
        hard: { count: 0, avgAccuracy: 0, fixtures: [] },
        complex: { count: 0, avgAccuracy: 0, fixtures: [] }
    };
    
    runs.forEach(run => {
        const fixture = fixtureData[run.fixture];
        const difficulty = fixture?.difficulty || 'medium';
        
        if (!tiers[difficulty]) {
            tiers.hard.count++;
            tiers.hard.fixtures.push(run.fixture);
            return;
        }
        
        tiers[difficulty].count++;
        tiers[difficulty].fixtures.push(run.fixture);
        tiers[difficulty].avgAccuracy += run.best_score || 0;
    });
    
    // Calculate averages
    Object.keys(tiers).forEach(tier => {
        if (tiers[tier].count > 0) {
            tiers[tier].avgAccuracy = tiers[tier].avgAccuracy / tiers[tier].count;
        }
    });
    
    return tiers;
}

/**
 * Get historical accuracy trend for a fixture
 * @param {string} fixtureName - Name of the fixture
 * @returns {Object[]} - Array of {timestamp, accuracy} objects
 */
function getFixtureTrend(fixtureName) {
    const runs = allData?.runs?.filter(r => r.fixture === fixtureName) || [];
    return runs
        .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
        .map(run => ({
            timestamp: parseTimestamp(run.timestamp),
            accuracy: run.best_score || 0,
            pitchAccuracy: run.pitch_accuracy,
            rhythmAccuracy: run.rhythm_accuracy
        }));
}

/**
 * Get aggregate accuracy trend (all fixtures combined)
 * @returns {Object[]} - Array of {timestamp, accuracy} objects
 */
function getAggregateTrend() {
    const grouped = {};
    
    allData?.runs?.forEach(run => {
        const dateKey = run.timestamp?.split('T')[0];
        if (!dateKey) return;
        
        if (!grouped[dateKey]) {
            grouped[dateKey] = [];
        }
        grouped[dateKey].push(run.best_score || 0);
    });
    
    return Object.entries(grouped)
        .map(([date, scores]) => ({
            timestamp: parseTimestamp(date),
            accuracy: scores.reduce((a, b) => a + b, 0) / scores.length
        }))
        .sort((a, b) => a.timestamp - b.timestamp);
}

/**
 * Get failure pattern summary from baseline results
 * @returns {Object} - Object with failure type counts
 */
function getFailureSummary() {
    const summary = {
        pitch: 0,
        rhythm: 0,
        structure: 0,
        notes: 0,
        other: 0
    };
    
    allData?.baselines?.forEach(baseline => {
        baseline.fixtures?.forEach(fixture => {
            if (fixture.failure_modes) {
                const grouped = groupByFailureType(fixture.failure_modes);
                Object.keys(summary).forEach(key => {
                    summary[key] += grouped[key] || 0;
                });
            }
        });
    });
    
    return summary;
}

/**
 * Get fixtures meeting 95% threshold
 * @returns {Object} - Object with count and list of fixtures
 */
function getFixturesMeetingThreshold() {
    const fixtures = new Set();
    let count = 0;
    
    allData?.runs?.forEach(run => {
        if (run.best_score >= 95) {
            fixtures.add(run.fixture);
        }
    });
    
    return {
        count: fixtures.size,
        fixtures: Array.from(fixtures)
    };
}

/**
 * Get fixture list with latest stats
 * @returns {Object[]} - Array of fixture info objects
 */
function getFixtureList() {
    const fixtureMap = {};
    
    // Group runs by fixture
    allData?.runs?.forEach(run => {
        const name = run.fixture;
        if (!fixtureMap[name]) {
            fixtureMap[name] = {
                name: name,
                runs: [],
                bestScore: 0,
                latestAccuracy: 0,
                trend: 'stable',
                difficulty: 'medium'
            };
        }
        
        fixtureMap[name].runs.push(run);
        fixtureMap[name].bestScore = Math.max(
            fixtureMap[name].bestScore,
            run.best_score || 0
        );
    });
    
    // Calculate latest and trend for each fixture
    Object.keys(fixtureMap).forEach(name => {
        const fixture = fixtureMap[name];
        fixture.runs.sort((a, b) => 
            new Date(a.timestamp) - new Date(b.timestamp)
        );
        
        const latest = fixture.runs[fixture.runs.length - 1];
        fixture.latestAccuracy = latest.best_score || 0;
        
        const scores = fixture.runs.map(r => r.best_score || 0);
        fixture.trend = calculateTrend(scores);
        
        // Get difficulty from baseline or iteration data
        const baselineData = allData?.baselines?.[0]?.fixtures?.find(f => f.name === name);
        const iterData = allData?.iterations?.find(i => i.fixture === name);
        fixture.difficulty = baselineData?.difficulty || iterData?.difficulty || 'medium';
    });
    
    return Object.values(fixtureMap).sort((a, b) => 
        b.latestAccuracy - a.latestAccuracy
    );
}

/**
 * Refresh all data (clears cache)
 * @returns {Promise<Object>} - Fresh data object
 */
async function refreshData() {
    allData = null;
    baselineData = null;
    iterationData = null;
    fixtureData = {};
    return fetchAllResults();
}
