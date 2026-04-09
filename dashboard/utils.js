/**
 * Utility functions for test accuracy dashboard
 */

/**
 * Calculate trend direction from an array of values
 * @param {number[]} values - Array of accuracy values
 * @returns {string} - 'up', 'down', or 'stable'
 */
function calculateTrend(values) {
    if (!values || values.length < 2) return 'stable';
    const recent = values.slice(-3); // Last 3 values
    const first = recent[0];
    const last = recent[recent.length - 1];
    const diff = last - first;
    
    if (diff > 1) return 'up';
    if (diff < -1) return 'down';
    return 'stable';
}

/**
 * Format percentage with proper decimal places
 * @param {number} value - Value to format
 * @param {number} decimals - Decimal places (default: 1)
 * @returns {string} - Formatted percentage string
 */
function formatPercent(value, decimals = 1) {
    if (value === null || value === undefined) return 'N/A';
    return value.toFixed(decimals) + '%';
}

/**
 * Get threshold status class based on 95% goal
 * @param {number} accuracy - Accuracy value
 * @returns {string} - CSS class: 'met', 'near', or 'missed'
 */
function getThresholdStatus(accuracy) {
    if (accuracy === null || accuracy === undefined) return 'unknown';
    if (accuracy >= 95) return 'met';
    if (accuracy >= 85) return 'near';
    return 'missed';
}

/**
 * Group failures by type
 * @param {string[]} failureModes - Array of failure mode strings
 * @returns {Object} - Object with failure types as keys and counts as values
 */
function groupByFailureType(failureModes) {
    const groups = {};
    const categories = {
        'pitch': ['wrong_pitch'],
        'rhythm': ['wrong_duration', 'wrong_tie'],
        'structure': ['wrong_key', 'wrong_time', 'extra_measure', 'missing_measure'],
        'notes': ['extra_note', 'missing_note', 'wrong_note_type']
    };
    
    // Initialize categories
    Object.keys(categories).forEach(cat => {
        groups[cat] = 0;
    });
    
    if (!failureModes) return groups;
    
    failureModes.forEach(mode => {
        for (const [category, modes] of Object.entries(categories)) {
            if (modes.includes(mode)) {
                groups[category]++;
                return;
            }
        }
        // Uncategorized failures
        if (!groups.other) groups.other = 0;
        groups.other++;
    });
    
    return groups;
}

/**
 * Parse timestamp in various formats
 * @param {string} timestamp - Timestamp string (ISO or other format)
 * @returns {Date} - Parsed Date object
 */
function parseTimestamp(timestamp) {
    if (!timestamp) return new Date();
    
    // Try ISO 8601 format
    if (timestamp.includes('T') || timestamp.includes('-')) {
        const date = new Date(timestamp);
        if (!isNaN(date.getTime())) return date;
    }
    
    // Try Unix timestamp
    const unix = parseInt(timestamp);
    if (!isNaN(unix) && unix > 1000000000) {
        return new Date(unix * 1000);
    }
    
    // Default to now
    return new Date();
}

/**
 * Format date for display
 * @param {string|Date} timestamp - Timestamp to format
 * @returns {string} - Formatted date string
 */
function formatDate(timestamp) {
    const date = parseTimestamp(timestamp);
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Calculate aggregate statistics
 * @param {Object[]} data - Array of data objects with numeric fields
 * @param {string} field - Field to aggregate
 * @returns {Object} - Object with avg, min, max, count
 */
function calculateStats(data, field) {
    const values = data.map(d => d[field]).filter(v => v !== null && v !== undefined);
    if (values.length === 0) return { avg: 0, min: 0, max: 0, count: 0 };
    
    const sum = values.reduce((a, b) => a + b, 0);
    return {
        avg: sum / values.length,
        min: Math.min(...values),
        max: Math.max(...values),
        count: values.length
    };
}

/**
 * Filter data by date range
 * @param {Object[]} data - Array of data objects with timestamp field
 * @param {Date} startDate - Start date (optional)
 * @param {Date} endDate - End date (optional)
 * @returns {Object[]} - Filtered data
 */
function filterByDateRange(data, startDate, endDate) {
    return data.filter(item => {
        const itemDate = parseTimestamp(item.timestamp);
        if (startDate && itemDate < startDate) return false;
        if (endDate && itemDate > endDate) return false;
        return true;
    });
}

/**
 * Group data by fixture name
 * @param {Object[]} data - Array of data objects with fixture field
 * @returns {Object} - Object with fixture names as keys and arrays as values
 */
function groupByFixture(data) {
    const groups = {};
    data.forEach(item => {
        const fixture = item.fixture || item.name;
        if (!groups[fixture]) groups[fixture] = [];
        groups[fixture].push(item);
    });
    return groups;
}
