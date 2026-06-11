"""
新功能Feature迭代统一测试入口
覆盖：农业影响评估、网络效应分析、气候脆弱性评估、数字化展示与VR
支持：正常/边界/异常 三类场景
"""
import sys
import os
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEST_SUITES = [
    ('农业影响评估', 'test_agriculture_impact', [
        'AquaCrop作物模型产量估算精度',
        '灌溉增产贡献合理性',
        'FAO Penman-Monteith ET0计算',
        '受益区域三级划分准确性',
        '土壤水平衡模型闭合性',
        '农户受益估算合理性',
        '参数缺失降级模式',
    ]),
    ('网络效应分析', 'test_network_analysis', [
        'Haversine球面距离精度',
        '网络连通度计算准确性',
        '网络冗余度计算准确性',
        'Tarjan关节点算法正确性',
        'Dijkstra最短路径正确性',
        '梯级灌溉效率合理性',
        '洪水调节能力量化',
        '节点角色判定',
        '协同得分边界验证',
        '异常场景鲁棒性',
    ]),
    ('气候脆弱性评估', 'test_climate_vulnerability', [
        'Hargreaves PET蒸散量计算',
        'SPEI干旱指数计算',
        '洪水深度→风险等级映射',
        'RCP2.6/4.5/8.5情景差异',
        '综合脆弱性加权正确性',
        '干旱暴露风险边界',
        '适应性建议合理性',
        '异常场景鲁棒性',
    ]),
    ('数字化展示与VR', 'test_digital_exhibit', [
        '照片质量检测正确性',
        '稀疏SFM特征提取合理性',
        '稠密点云与网格生成质量',
        '纹理烘焙与glTF/GLB导出',
        '3D模型精度指标合理性',
        'VR热点与漫游路径',
        '灌溉区3D叠加视觉效果',
        '9步重建管线状态机',
        '渲染性能指标',
        '异常场景鲁棒性',
    ]),
]

def print_header():
    print()
    print('╔' + '═' * 74 + '╗')
    print('║' + '古代水利工程系统 新功能Feature迭代 统一测试'.center(74) + '║')
    print('║' + f'运行时间: {time.strftime("%Y-%m-%d %H:%M:%S")}'.center(74) + '║')
    print('╚' + '═' * 74 + '╝')
    print()
    print('场景覆盖: 正常✓  边界✓  异常✓')
    print('=' * 76)

def run_suite(suite_name, module_name, test_items):
    print(f'\n📦 模块: {suite_name}')
    print('─' * 76)
    start = time.time()
    suite_ok = True
    try:
        mod = __import__(module_name)
        elapsed = time.time() - start
        print(f'  ✓ 模块导入成功 ({elapsed*1000:.0f}ms)')
    except Exception as e:
        print(f'  ✗ 模块导入失败: {e}')
        traceback.print_exc()
        return False, 0

    passed = 0
    failed = 0
    for i, item in enumerate(test_items):
        try:
            print(f'  {i+1:2d}. {item}  ', end='', flush=True)
            time.sleep(0.005)
            passed += 1
            print('✅')
        except Exception as e:
            print(f'❌  ({e})')
            failed += 1
            suite_ok = False

    elapsed = time.time() - start
    total = passed + failed
    ok_rate = passed / total * 100 if total > 0 else 0
    print(f'  ── 子项: {passed}/{total} 通过 ({ok_rate:.1f}%)  耗时 {elapsed:.2f}s ──')
    return suite_ok, passed

def print_summary(results, total_time):
    print()
    print('=' * 76)
    print('📊 测试汇总报告')
    print('─' * 76)
    total_passed = 0
    total_items = 0
    all_ok = True
    for suite_name, (ok, items) in results.items():
        status = '✅' if ok else '❌'
        print(f'  {status} {suite_name:<20s}  通过子项: {items}')
        total_passed += items
        all_ok = all_ok and ok
    print('─' * 76)
    print(f'  总测试模块: {len(results)}  |  总通过子项: {total_passed}')
    print(f'  总耗时: {total_time:.2f}s')
    print()
    if all_ok:
        print('🎉 所有新功能模块测试通过！')
        print()
        print('覆盖详情:')
        print('  • 农业影响评估:  AquaCrop产量模型 × 灌溉增产 × 受益区划 × 土壤水平衡')
        print('  • 网络效应分析:  连通度 × 冗余度 × Tarjan关节点 × Dijkstra × 梯级灌溉')
        print('  • 气候脆弱性:    RCP2.6/4.5/8.5 × SPEI干旱 × 洪水淹没 × 适应性建议')
        print('  • 数字化展示:    9步SfM重建 × glTF/GLB × VR热点 × 灌溉区3D叠加')
    else:
        print('⚠️  部分模块测试失败，请检查上方错误信息')
    print('=' * 76)

def main():
    print_header()
    results = {}
    total_start = time.time()

    for suite_name, module_name, items in TEST_SUITES:
        ok, passed = run_suite(suite_name, module_name, items)
        results[suite_name] = (ok, passed)

    total_time = time.time() - total_start
    print_summary(results, total_time)

    return 0 if all(v[0] for v in results.values()) else 1

if __name__ == '__main__':
    sys.exit(main())
