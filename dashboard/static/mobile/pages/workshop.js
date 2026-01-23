/**
 * Workshop Page Module - Kanban & Agents
 */
const WorkshopModule = {
    kanban: {
        tasks: [],
        async load() {
            try { const r = await MobileAPI.getTasks(); this.tasks = r.tasks || []; return this.tasks; }
            catch { return []; }
        },
        getByColumn(col) {
            const map = { 'todo': ['todo', 'To Do', null], 'progress': ['progress', 'In Progress'], 'done': ['done', 'Done'] };
            return this.tasks.filter(t => (map[col] || [col]).includes(t.column));
        }
    },
    agents: {
        list: [],
        defaults: [
            { id: 'claude', name: 'Claude', avatar: '&#129302;', status: 'ready' },
            { id: 'researcher', name: 'Researcher', avatar: '&#128269;', status: 'idle' },
            { id: 'coder', name: 'Coder', avatar: '&#128187;', status: 'ready' },
            { id: 'writer', name: 'Writer', avatar: '&#9997;', status: 'ready' }
        ],
        async load() {
            try { const r = await MobileAPI.getAgents(); this.list = r.agents?.length ? r.agents : this.defaults; }
            catch { this.list = this.defaults; }
            return this.list;
        }
    }
};
window.WorkshopModule = WorkshopModule;
