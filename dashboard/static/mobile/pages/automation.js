/**
 * Automation Page Module - Job Management
 */
const AutomationModule = {
    jobs: [],
    async loadJobs() {
        try { const r = await MobileAPI.getJobs(); this.jobs = r.jobs || r || []; }
        catch { this.jobs = []; }
        return this.jobs;
    },
    getFiltered(filter) {
        if (filter === 'active') return this.jobs.filter(j => j.enabled !== false);
        if (filter === 'disabled') return this.jobs.filter(j => j.enabled === false);
        return this.jobs;
    },
    getStats() {
        const total = this.jobs.length;
        const active = this.jobs.filter(j => j.enabled !== false).length;
        const failed = this.jobs.filter(j => j.last_status === 'failed' || j.last_status === 'error').length;
        return { total, active, failed, successRate: total ? Math.round(((total - failed) / total) * 100) : 100 };
    }
};
window.AutomationModule = AutomationModule;
