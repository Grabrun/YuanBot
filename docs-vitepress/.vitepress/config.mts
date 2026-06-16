import { defineConfig } from 'vitepress'

export default defineConfig({
  // 部署路径 — GitHub Pages: grabrun.github.io/YuanBot/
  base: '/YuanBot/',

  title: 'YuanBot',
  description: '有记忆、有情感、会主动想起你的开源 AI 虚拟伴侣',

  lastUpdated: true,
  cleanUrls: true,
  ignoreDeadLinks: true,

  head: [
    ['link', { rel: 'icon', href: '/YuanBot/favicon.ico' }],
    ['meta', { name: 'theme-color', content: '#4d6bfe' }],
  ],

  themeConfig: {
    logo: '/YuanBot/logo.png',

    socialLinks: [
      { icon: 'github', link: 'https://github.com/Grabrun/YuanBot' },
    ],

    // 编辑链接指向 GitHub
    editLink: {
      pattern: 'https://github.com/Grabrun/YuanBot/edit/main/docs-vitepress/:path',
    },

    footer: {
      message: 'Made with 🌸 by Grabrun',
      copyright: 'Copyright © 2026 YuanBot Team',
    },
  },

  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      title: 'YuanBot',
      description: '有记忆、有情感、会主动想起你的开源 AI 虚拟伴侣',
      themeConfig: {
        nav: [
          { text: '首页', link: '/' },
          { text: '指南', link: '/guide/getting-started' },
          { text: 'API 参考', link: '/api/reference' },
          { text: '社区', link: '/community/contributing' },
          { text: 'GitHub', link: 'https://github.com/Grabrun/YuanBot' },
        ],
        sidebar: {
          '/guide/': [
            {
              text: '入门指南',
              items: [
                { text: '快速开始', link: '/guide/getting-started' },
                { text: '安装指南', link: '/guide/installation' },
                { text: '配置说明', link: '/guide/configuration' },
              ],
            },
            {
              text: '设计文档',
              items: [
                { text: '总体架构', link: '/guide/design/architecture-v1.5' },
                { text: 'AI 提供商', link: '/guide/design/ai-provider-system-v2' },
                { text: '记忆与情感', link: '/guide/design/memory-emotion-system' },
                { text: '人格与决策', link: '/guide/design/persona-decision-system' },
                { text: '能力与工具', link: '/guide/design/capability-tool-system' },
                { text: '语音合成', link: '/guide/design/tts-system' },
                { text: '主动陪伴', link: '/guide/design/proactive-companion-system' },
                { text: '接入与通信', link: '/guide/design/gateway-communication-system' },
              ],
            },
          ],
          '/api/': [
            {
              text: 'API 文档',
              items: [
                { text: 'API 参考', link: '/api/reference' },
              ],
            },
          ],
          '/channels-apis/': [
            {
              text: '通道适配器 API',
              items: [
                { text: 'NapCat API', link: '/channels-apis/napcat-api' },
                { text: 'WeChat iLink API', link: '/channels-apis/openclaw-weixin-api' },
              ],
            },
          ],
          '/community/': [
            {
              text: '社区',
              items: [
                { text: '参与贡献', link: '/community/contributing' },
              ],
            },
          ],
        },
        outline: {
          label: '页面内容',
        },
        docFooter: {
          prev: '上一页',
          next: '下一页',
        },
        lastUpdated: {
          text: '最后更新',
        },
        darkModeSwitchLabel: '切换主题',
        sidebarMenuLabel: '菜单',
        returnToTopLabel: '返回顶部',
        langMenuLabel: '语言',
      },
    },
    en: {
      label: 'English',
      lang: 'en-US',
      title: 'YuanBot',
      description: 'An open-source AI virtual companion with memory, emotions, and proactive care',
      themeConfig: {
        nav: [
          { text: 'Home', link: '/en/' },
          { text: 'Guide', link: '/en/guide/getting-started' },
          { text: 'API', link: '/en/api/reference' },
          { text: 'Community', link: '/en/community/contributing' },
          { text: 'GitHub', link: 'https://github.com/Grabrun/YuanBot' },
        ],
        sidebar: {
          '/en/guide/': [
            {
              text: 'Getting Started',
              items: [
                { text: 'Quick Start', link: '/en/guide/getting-started' },
                { text: 'Installation', link: '/en/guide/installation' },
                { text: 'Configuration', link: '/en/guide/configuration' },
              ],
            },
          ],
          '/en/api/': [
            {
              text: 'API',
              items: [
                { text: 'API Reference', link: '/en/api/reference' },
              ],
            },
          ],
          '/en/community/': [
            {
              text: 'Community',
              items: [
                { text: 'Contributing', link: '/en/community/contributing' },
              ],
            },
          ],
        },
        outline: {
          label: 'On this page',
        },
        docFooter: {
          prev: 'Previous',
          next: 'Next',
        },
        lastUpdated: {
          text: 'Last updated',
        },
        darkModeSwitchLabel: 'Appearance',
        sidebarMenuLabel: 'Menu',
        returnToTopLabel: 'Back to top',
        langMenuLabel: 'Language',
      },
    },
    ja: {
      label: '日本語',
      lang: 'ja-JP',
      title: 'YuanBot',
      description: '記憶と感情を持ち、自ら寄り添うオープンソースAIバーチャルコンパニオン',
      themeConfig: {
        nav: [
          { text: 'ホーム', link: '/ja/' },
          { text: 'ガイド', link: '/ja/guide/getting-started' },
          { text: 'API', link: '/ja/api/reference' },
          { text: 'コミュニティ', link: '/ja/community/contributing' },
          { text: 'GitHub', link: 'https://github.com/Grabrun/YuanBot' },
        ],
        sidebar: {
          '/ja/guide/': [
            {
              text: 'スタートガイド',
              items: [
                { text: 'クイックスタート', link: '/ja/guide/getting-started' },
                { text: 'インストール', link: '/ja/guide/installation' },
                { text: '設定', link: '/ja/guide/configuration' },
              ],
            },
          ],
          '/ja/api/': [
            {
              text: 'API',
              items: [
                { text: 'APIリファレンス', link: '/ja/api/reference' },
              ],
            },
          ],
          '/ja/community/': [
            {
              text: 'コミュニティ',
              items: [
                { text: '貢献する', link: '/ja/community/contributing' },
              ],
            },
          ],
        },
        outline: {
          label: '目次',
        },
        docFooter: {
          prev: '前へ',
          next: '次へ',
        },
        lastUpdated: {
          text: '最終更新',
        },
        darkModeSwitchLabel: 'テーマ切替',
        sidebarMenuLabel: 'メニュー',
        returnToTopLabel: 'トップへ戻る',
        langMenuLabel: '言語',
      },
    },
  },
})

// trigger redeploy
