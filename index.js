#!/usr/bin/env node
/**
 * Claude Harness Kit (CHK) - Claude Code Plugin Entry Point
 *
 * This plugin provides:
 * - 22 specialized Agents (architect, orchestrator, code-reviewer, etc.)
 * - 19 Skills (tdd, testing, debugging, etc.)
 * - 6 Rules (collaboration, security, quality-gates, etc.)
 * - Hook system for session management, safety checks, quality gates
 * - evolve-daemon for continuous learning
 *
 * Usage:
 *   In Claude Code, use natural language to invoke CHK capabilities:
 *   - "分析一下如何实现这个功能"
 *   - "使用 architect Agent 设计架构"
 *   - "用 ralph 模式重写支付模块"
 */

const path = require('path');
const fs = require('fs');

const PLUGIN_ROOT = __dirname;
const AGENTS_DIR = path.join(PLUGIN_ROOT, 'agents');
const SKILLS_DIR = path.join(PLUGIN_ROOT, 'skills');
const RULES_DIR = path.join(PLUGIN_ROOT, 'rules');
const HOOKS_DIR = path.join(PLUGIN_ROOT, 'hooks');

// Load agents
function loadAgents() {
    const agents = {};
    if (fs.existsSync(AGENTS_DIR)) {
        fs.readdirSync(AGENTS_DIR).forEach(file => {
            if (file.endsWith('.md')) {
                const name = file.replace('.md', '');
                agents[name] = path.join(AGENTS_DIR, file);
            }
        });
    }
    return agents;
}

// Load skills
function loadSkills() {
    const skills = {};
    if (fs.existsSync(SKILLS_DIR)) {
        fs.readdirSync(SKILLS_DIR).forEach(dir => {
            const skillPath = path.join(SKILLS_DIR, dir);
            if (fs.statSync(skillPath).isDirectory()) {
                skills[dir] = skillPath;
            }
        });
    }
    return skills;
}

// Load rules
function loadRules() {
    const rules = {};
    if (fs.existsSync(RULES_DIR)) {
        fs.readdirSync(RULES_DIR).forEach(file => {
            if (file.endsWith('.md')) {
                const name = file.replace('.md', '');
                rules[name] = path.join(RULES_DIR, file);
            }
        });
    }
    return rules;
}

// Plugin info
const pluginInfo = {
    name: 'claude-harness-kit',
    version: '0.6.1',
    description: 'Claude Harness Kit — Human steers, Agents execute. 多 Agent 协作、通用 Skills、持续进化',
    agents: Object.keys(loadAgents()),
    skills: Object.keys(loadSkills()),
    rules: Object.keys(loadRules()),
    hooks: fs.existsSync(HOOKS_DIR) ? fs.readdirSync(HOOKS_DIR).filter(f => f.endsWith('.json')).length : 0,
};

// Auto-load agents and skills on Claude Code startup
module.exports = {
    // Plugin metadata
    getInfo: () => pluginInfo,

    // Get all available agents
    getAgents: loadAgents,

    // Get all available skills
    getSkills: loadSkills,

    // Get all available rules
    getRules: loadRules,

    // Get hooks configuration
    getHooks: () => {
        const hooksPath = path.join(HOOKS_DIR, 'hooks.json');
        if (fs.existsSync(hooksPath)) {
            return JSON.parse(fs.readFileSync(hooksPath, 'utf-8'));
        }
        return null;
    },

    // Initialize plugin
    init: () => {
        console.log('✓ Claude Harness Kit (CHK) v0.6.1 loaded');
        console.log(`  Agents: ${pluginInfo.agents.length}`);
        console.log(`  Skills: ${pluginInfo.skills.length}`);
        console.log(`  Rules: ${pluginInfo.rules.length}`);
    }
};

// Auto-initialize when loaded
module.exports.init();