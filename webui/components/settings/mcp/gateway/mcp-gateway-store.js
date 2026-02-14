import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const model = {
	// UI state
	loading: false,
	error: null,
	activeView: "servers", // "servers" | "pool" | "discover" | "catalog"
	showForm: false,
	editingServer: null,

	// Data
	servers: [],
	poolStatus: null,
	discoveryResults: [],
	discoveryQuery: "",
	catalogEntries: [],
	catalogYaml: "",

	// Form defaults
	formData: {
		name: "",
		transport_type: "streamable_http",
		url: "",
		command: "",
		args: "",
		docker_image: "",
		required_roles: "",
		is_enabled: true,
	},

	// ---------- Lifecycle ----------

	async init() {
		await this.loadServers();
	},

	// ---------- Server CRUD ----------

	async loadServers() {
		this.loading = true;
		this.error = null;
		try {
			const res = await callJsonApi("/mcp_gateway_servers", {
				action: "list",
			});
			this.servers = res.data || [];
		} catch (e) {
			this.error = e.message;
		}
		this.loading = false;
	},

	async createServer() {
		this.error = null;
		try {
			const data = {
				action: "create",
				name: this.formData.name,
				transport_type: this.formData.transport_type,
				is_enabled: this.formData.is_enabled,
			};
			if (this.formData.url) data.url = this.formData.url;
			if (this.formData.command) data.command = this.formData.command;
			if (this.formData.args) {
				data.args = this.formData.args
					.split(",")
					.map((s) => s.trim())
					.filter(Boolean);
			}
			if (this.formData.docker_image)
				data.docker_image = this.formData.docker_image;
			if (this.formData.required_roles) {
				data.required_roles = this.formData.required_roles
					.split(",")
					.map((s) => s.trim())
					.filter(Boolean);
			}

			const res = await callJsonApi("/mcp_gateway_servers", data);
			if (res.ok) {
				this.showForm = false;
				this.resetForm();
				await this.loadServers();
			} else {
				this.error = res.error || "Failed to create server";
			}
		} catch (e) {
			this.error = e.message;
		}
	},

	async deleteServer(name) {
		this.error = null;
		try {
			const res = await callJsonApi("/mcp_gateway_servers", {
				action: "delete",
				name,
			});
			if (res.ok) {
				await this.loadServers();
			} else {
				this.error = res.error || "Failed to delete server";
			}
		} catch (e) {
			this.error = e.message;
		}
	},

	async toggleServer(name, enabled) {
		this.error = null;
		try {
			await callJsonApi("/mcp_gateway_servers", {
				action: "update",
				name,
				is_enabled: enabled,
			});
			await this.loadServers();
		} catch (e) {
			this.error = e.message;
		}
	},

	async getServerStatus(name) {
		try {
			const res = await callJsonApi("/mcp_gateway_servers", {
				action: "status",
				name,
			});
			return res.data || {};
		} catch (e) {
			this.error = e.message;
			return {};
		}
	},

	// ---------- Connection Pool ----------

	async loadPoolStatus() {
		this.loading = true;
		this.error = null;
		try {
			const res = await callJsonApi("/mcp_gateway_pool", {
				action: "status",
			});
			this.poolStatus = res.data || null;
		} catch (e) {
			this.error = e.message;
		}
		this.loading = false;
	},

	async runHealthCheck() {
		this.error = null;
		try {
			const res = await callJsonApi("/mcp_gateway_pool", {
				action: "health_check",
			});
			if (res.ok) {
				await this.loadPoolStatus();
			}
			return res.data || {};
		} catch (e) {
			this.error = e.message;
			return {};
		}
	},

	async evictConnection(name) {
		this.error = null;
		try {
			await callJsonApi("/mcp_gateway_pool", {
				action: "evict",
				name,
			});
			await this.loadPoolStatus();
		} catch (e) {
			this.error = e.message;
		}
	},

	// ---------- Discovery ----------

	async searchRegistry(query) {
		this.loading = true;
		this.error = null;
		this.discoveryQuery = query || "";
		try {
			const res = await callJsonApi("/mcp_gateway_discover", {
				action: "search",
				query: this.discoveryQuery,
				limit: 20,
			});
			this.discoveryResults = res.data || [];
		} catch (e) {
			this.error = e.message;
		}
		this.loading = false;
	},

	async installFromRegistry(serverData) {
		this.error = null;
		try {
			const res = await callJsonApi("/mcp_gateway_discover", {
				action: "install",
				server: serverData,
			});
			if (res.ok) {
				await this.loadServers();
				this.setView("servers");
			} else {
				this.error = res.error || "Failed to install server";
			}
		} catch (e) {
			this.error = e.message;
		}
	},

	// ---------- Docker Catalog ----------

	async browseCatalog(yamlContent) {
		this.loading = true;
		this.error = null;
		this.catalogYaml = yamlContent || "";
		try {
			const res = await callJsonApi("/mcp_gateway_catalog", {
				action: "browse",
				yaml: this.catalogYaml,
			});
			if (res.ok) {
				this.catalogEntries = res.data || [];
			} else {
				this.error = res.error || "Failed to parse catalog";
			}
		} catch (e) {
			this.error = e.message;
		}
		this.loading = false;
	},

	async installFromCatalog(entry) {
		this.error = null;
		try {
			const res = await callJsonApi("/mcp_gateway_catalog", {
				action: "install",
				entry,
			});
			if (res.ok) {
				await this.loadServers();
				this.setView("servers");
			} else {
				this.error = res.error || "Failed to install from catalog";
			}
		} catch (e) {
			this.error = e.message;
		}
	},

	// ---------- UI helpers ----------

	openForm() {
		this.resetForm();
		this.showForm = true;
		this.editingServer = null;
	},

	resetForm() {
		this.formData = {
			name: "",
			transport_type: "streamable_http",
			url: "",
			command: "",
			args: "",
			docker_image: "",
			required_roles: "",
			is_enabled: true,
		};
	},

	setView(view) {
		this.activeView = view;
		if (view === "pool") this.loadPoolStatus();
		else if (view === "discover") this.searchRegistry(this.discoveryQuery);
		else this.loadServers();
	},

	transportLabel(type) {
		const labels = {
			streamable_http: "HTTP",
			sse: "SSE",
			stdio: "Stdio",
		};
		return labels[type] || type;
	},
};

export const store = createStore("mcpGateway", model);
