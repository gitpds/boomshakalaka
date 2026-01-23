/**
 * BOOMSHAKALAKA MOBILE - API Client
 */

const MobileAPI = {
    async request(endpoint, options = {}) {
        const config = {
            method: 'GET',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            ...options
        };

        try {
            const response = await fetch(endpoint, config);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const contentType = response.headers.get('content-type');
            return contentType?.includes('application/json') ? await response.json() : await response.text();
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    },

    get(endpoint) { return this.request(endpoint); },
    post(endpoint, data) { return this.request(endpoint, { method: 'POST', body: JSON.stringify(data) }); },
    put(endpoint, data) { return this.request(endpoint, { method: 'PUT', body: JSON.stringify(data) }); },
    delete(endpoint) { return this.request(endpoint, { method: 'DELETE' }); },

    // Health & Status
    getHealth() { return this.get('/api/health'); },
    getStats() { return this.get('/api/stats'); },

    // Kanban / Tasks
    getTasks() { return this.get('/api/kanban/tasks'); },
    createTask(task) { return this.post('/api/kanban/tasks', task); },
    updateTask(taskId, updates) { return this.put(`/api/kanban/tasks/${taskId}`, updates); },
    deleteTask(taskId) { return this.delete(`/api/kanban/tasks/${taskId}`); },
    moveTask(taskId, column) { return this.post(`/api/kanban/tasks/${taskId}/move`, { column }); },

    // Agents
    getAgents() { return this.get('/api/agents'); },

    // Automation / Cron Jobs
    getJobs() { return this.get('/api/cron'); },
    triggerJob(jobName) { return this.post(`/api/cron/${jobName}/trigger`); },
    toggleJob(jobName) { return this.post(`/api/cron/${jobName}/toggle`); },
    getJobLogs(jobName, lines = 100) { return this.get(`/api/logs/${jobName}?lines=${lines}`); },

    // Reggie Robot
    getReggieStatus() { return this.get('/api/reggie/status'); },
    setReggieControl(control, value) { return this.post('/api/reggie/control', { control, value }); },
    setReggiePosition(positions) { return this.post('/api/reggie/position', positions); },
    applyReggiePreset(presetName) { return this.post(`/api/reggie/presets/${presetName}/apply`); },
    getMoves() { return this.get('/api/reggie/moves'); },
    playMove(moveId) { return this.post(`/api/reggie/moves/${moveId}/play`); },
    stopMove() { return this.post('/api/reggie/moves/stop'); },
    getHuggingFaceApps() { return this.get('/api/reggie/apps'); },
    startApp(appId) { return this.post(`/api/reggie/apps/${appId}/start`); },
    stopApp(appId) { return this.post(`/api/reggie/apps/${appId}/stop`); },
    setVolume(level) { return this.post('/api/reggie/volume', { level }); },
    getDaemonStatus() { return this.get('/api/reggie/daemon/status'); },
    restartDaemon() { return this.post('/api/reggie/daemon/restart'); }
};

window.MobileAPI = MobileAPI;
