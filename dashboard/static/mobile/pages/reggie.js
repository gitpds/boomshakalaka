/**
 * Reggie Page Module - Robot Control
 */
const ReggieModule = {
    status: null,
    positions: {},
    defaults: { head_tilt: 90, head_pan: 90, body_rotate: 90, body_lean: 90, antenna_left: 90, antenna_right: 90 },

    async getStatus() {
        try { this.status = await MobileAPI.getReggieStatus(); if (this.status?.positions) this.positions = this.status.positions; }
        catch { this.status = null; }
        return this.status;
    },
    isConnected() { return this.status?.connected; },

    async setControl(control, value) { await MobileAPI.setReggieControl(control, value); this.positions[control] = value; },
    async setPosition(positions) { await MobileAPI.setReggiePosition(positions); Object.assign(this.positions, positions); },
    async resetSection(section) {
        const map = { head: ['head_tilt', 'head_pan'], body: ['body_rotate', 'body_lean'], antenna: ['antenna_left', 'antenna_right'] };
        const pos = {}; (map[section] || []).forEach(c => pos[c] = this.defaults[c]);
        await this.setPosition(pos);
    },

    presets: {
        neutral: { head_tilt: 90, head_pan: 90, body_rotate: 90, body_lean: 90, antenna_left: 90, antenna_right: 90 },
        attentive: { head_tilt: 80, head_pan: 90, body_lean: 85, antenna_left: 120, antenna_right: 120 },
        relaxed: { head_tilt: 100, head_pan: 90, body_lean: 95, antenna_left: 60, antenna_right: 60 },
        curious: { head_tilt: 75, head_pan: 110, body_rotate: 100, antenna_left: 110, antenna_right: 70 },
        excited: { head_tilt: 70, head_pan: 90, body_lean: 80, antenna_left: 140, antenna_right: 140 },
        sleepy: { head_tilt: 110, head_pan: 90, body_lean: 100, antenna_left: 45, antenna_right: 45 }
    },
    async applyPreset(name) { await MobileAPI.applyReggiePreset(name); Object.assign(this.positions, this.presets[name] || {}); },

    currentMove: null,
    async playMove(id) { await MobileAPI.playMove(id); this.currentMove = id; },
    async stopMove() { await MobileAPI.stopMove(); this.currentMove = null; },

    apps: {
        list: [],
        defaults: [
            { id: 'chat', name: 'Chat Assistant', icon: '&#128172;', model: 'llama-2-7b', status: 'stopped' },
            { id: 'image_caption', name: 'Image Caption', icon: '&#128247;', model: 'blip', status: 'stopped' },
            { id: 'emotion_detect', name: 'Emotion Detection', icon: '&#128522;', model: 'facial-emotions', status: 'stopped' },
            { id: 'speech_recognize', name: 'Speech Recognition', icon: '&#127908;', model: 'whisper', status: 'stopped' }
        ],
        async load() { try { const r = await MobileAPI.getHuggingFaceApps(); this.list = r.apps?.length ? r.apps : this.defaults; } catch { this.list = this.defaults; } return this.list; }
    }
};
window.ReggieModule = ReggieModule;
