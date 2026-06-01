# 决策插件配置目录
# 在此目录下创建 .yaml 文件来注册自定义决策插件。
#
# 配置格式:
#   plugin_id: "unique_plugin_id"
#   module: "python.module.path.PluginClassName"
#   enabled: true
#   priority: 100  # 数值越小越先执行
#   config:
#     key: value
#
# 设计参考: persona-decision-system.md 第7.2节
