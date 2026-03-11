document.addEventListener('alpine:init', () => {
    Alpine.data('dashboard', () => ({
        botStatus: {},
        config: {
            persona: '',
            temperature: 0.9
        },
        memory: {},
        saving: false,
        saveSuccess: false,
        memoryLoading: false,
        
        init() {
            this.fetchStatus();
            this.fetchConfig();
            this.fetchMemory();
            
            // Auto-refresh loops
            setInterval(() => this.fetchStatus(), 3000);  // Every 3s
            setInterval(() => this.fetchMemory(), 5000);  // Every 5s
        },
        
        async fetchStatus() {
            try {
                const res = await fetch('/api/status');
                if (res.ok) {
                    this.botStatus = await res.json();
                }
            } catch (err) {
                console.error("Failed to fetch status", err);
                this.botStatus = { status: 'offline', ping: '--', guild_count: 0, active_voices: [] };
            }
        },
        
        async fetchConfig() {
            try {
                const res = await fetch('/api/config');
                if (res.ok) {
                    this.config = await res.json();
                }
            } catch (err) {
                console.error("Failed to fetch config", err);
            }
        },
        
        async fetchMemory() {
            this.memoryLoading = true;
            try {
                const res = await fetch('/api/memory');
                if (res.ok) {
                    this.memory = await res.json();
                }
            } catch (err) {
                console.error("Failed to fetch memory", err);
            } finally {
                this.memoryLoading = false;
            }
        },
        
        async saveConfig() {
            this.saving = true;
            this.saveSuccess = false;
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        persona: this.config.persona,
                        temperature: parseFloat(this.config.temperature)
                    })
                });
                
                if (res.ok) {
                    this.saveSuccess = true;
                    setTimeout(() => { this.saveSuccess = false; }, 3000);
                }
            } catch (err) {
                console.error("Failed to save config", err);
                alert("حدث خطأ أثناء حفظ الإعدادات!");
            } finally {
                this.saving = false;
            }
        }
    }));
});
