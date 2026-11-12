/**
 * 对比分析页面的端到端冒烟测试（jsdom + 真实后端）。
 *
 * 覆盖：打开方案 → 字段映射面板 → 启动比较 → 矩阵取数 → 双击格子证据 → 隔离区裁决 → 左右交换。
 * 运行前先启动后端（127.0.0.1:8000），然后：
 *   NODE_OPTIONS="--import ./scripts/smoke-preload.mjs" npx vite-node scripts/smoke-compare.mjs
 */
const nodeFetch = globalThis.fetch
globalThis.fetch = (url, init) => {
  const target = String(url).startsWith('http') ? String(url) : `http://127.0.0.1:8000${String(url)}`
  return nodeFetch(target, init)
}

const { mount } = await import('@vue/test-utils')
const { createRouter, createMemoryHistory, RouterView } = await import('vue-router')
const { createPinia } = await import('pinia')
const { h } = await import('vue')

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { render: () => h('div', 'home') } },
    { path: '/compare', component: (await import('@/views/compare/index.vue')).default },
    { path: '/query', component: (await import('@/views/query/index.vue')).default },
  ],
})
await router.push('/compare')
await router.isReady()

const wrapper = mount(RouterView, {
  global: { plugins: [router, createPinia()] },
  attachTo: document.getElementById('app'),
})

const failures = []
function check(condition, message) {
  console.log(`${condition ? 'PASS' : 'FAIL'} · ${message}`)
  if (!condition) failures.push(message)
}

async function settle(ms = 400) {
  await new Promise((resolve) => setTimeout(resolve, ms))
  await wrapper.vm.$nextTick()
}

await settle(900)
check(wrapper.findAll('.plan-row').length >= 3, '方案列表加载出 3 条以上记录')

const firstRow = wrapper.findAll('.plan-row')[0]
await firstRow.trigger('click')
await settle(900)

check(wrapper.find('[data-panel="mapping"]').exists(), '字段映射面板已渲染')
check(wrapper.findAll('.side-card').length === 2, '基准/对照两侧字段卡片各一张')
check(wrapper.findAll('.picker-item option').length >= 5, '数据集选择器可选多条数据集')
check(wrapper.findAll('.pair-row').length >= 1, '业务键映射行存在')
check(wrapper.findAll('.pair-table-row').length >= 2, '数值字段映射行存在')
check(
  wrapper.findAll('.alert.danger').every((node) => node.text().includes('映射不成立') === false),
  '字段映射没有校验错误',
)

const confirmButton = wrapper.findAll('.panel-actions button').find((node) => node.text().includes('确认映射'))
check(Boolean(confirmButton), '存在“确认映射并登记”按钮')
await confirmButton.trigger('click')
await settle(700)
check(wrapper.text().includes('字段映射已登记'), '映射保存成功并给出反馈')

const startButton = wrapper.findAll('.panel-actions button').find((node) => node.text().includes('启动比较'))
check(Boolean(startButton), '存在“启动比较”按钮')
await startButton.trigger('click')
await settle(1600)

check(wrapper.find('[data-panel="matrix"]').exists(), '差异矩阵已渲染')
const summaryCards = wrapper.findAll('.summary-card')
check(summaryCards.length === 6, '矩阵摘要卡片 6 张')
const cellCount = wrapper.findAll('.matrix-cell').length
check(cellCount >= 40, `矩阵格子渲染 ${cellCount} 个（分页 20 组 × 2 字段）`)
check(wrapper.findAll('.matrix-cell.cell-diff').length > 0, '存在超阈值红色格子')
check(wrapper.findAll('.matrix-cell.cell-null').length > 0, '存在空值紫色格子')
check(wrapper.findAll('.matrix-cell.cell-missing').length > 0, '存在缺行斜纹格子')
check(wrapper.findAll('.quarantine-group').length >= 3, '隔离区列出歧义键组')

const legendText = wrapper.find('.legend-row').text()
check(legendText.includes('数值差') && legendText.includes('缺行') && legendText.includes('空值'), '图例包含数值差、缺行、空值')

// 双击格子打开证据弹窗
const nullCell = wrapper.findAll('.matrix-cell.cell-null')[0]
await nullCell.trigger('dblclick')
await settle(700)
check(wrapper.find('[data-dialog="cell-evidence"]').exists(), '双击格子打开样本证据弹窗')
check(wrapper.text().includes('空字符串'), '证据弹窗区分空字符串与数字零')
const queryButtons = wrapper.findAll('[data-dialog="cell-evidence"] button').filter((node) => node.text().includes('在交互查询中打开'))
check(queryButtons.length === 2, '证据弹窗两侧各有一个交互查询跳转')
await queryButtons[0].trigger('click')
await settle(700)
check(router.currentRoute.value.path === '/query', '跳转到交互查询模块')
check(wrapper.text().includes('来自对比分析的样本证据'), '交互查询页展示证据定位横幅')
check(wrapper.findAll('.focus-row').length === 1, '对应查询语句被高亮')

// 回到对比页继续裁决隔离区
await router.push('/compare')
await settle(900)
const reopened = wrapper.findAll('.plan-row')[0]
await reopened.trigger('click')
await settle(900)
// 搏一个两侧都重复的键组（空业务键组只有基准侧一行，不能用于此检查）
const groups = wrapper.findAll('.quarantine-group')
const group = groups.find((node) => node.findAll('input[type="radio"]').length >= 4)
check(Boolean(group), '找到两侧都有多行记录的隔离键组')
check(groups.length >= 3, '隔离区列出歧义键组')
const radios = group.findAll('input[type="radio"]')
check(radios.length >= 4, '隔离区两侧记录都列出来了')
await radios[0].setValue()
await radios[3].setValue()
const confirmPair = group.findAll('button').find((node) => node.text().includes('确认这两条配对'))
check(Boolean(confirmPair), '存在“确认这两条配对”按钮')
await confirmPair.trigger('click')
await settle(1200)
check(wrapper.text().includes('已裁决：确认配对'), '隔离组裁决结果写回并可见')

const swapButton = wrapper.findAll('.panel-actions button').find((node) => node.text().includes('左右交换'))
check(Boolean(swapButton), '存在“左右交换”按钮')
await swapButton.trigger('click')
await settle(1500)
check(wrapper.text().includes('左右已交换'), '左右交换生成了独立轮次')
const swappedDiff = wrapper.findAll('.matrix-cell.cell-diff')
if (swappedDiff.length) {
  check(
    swappedDiff.some((cell) => cell.text().includes('-')),
    '交换后差值方向出现负数（方向取反）',
  )
}

if (failures.length) {
  console.error(`\n${failures.length} 项失败：`)
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}
console.log('\n全部冒烟检查通过')
process.exit(0)
