/**
 * 受益区与增产热力渲染器 - 兼容层
 * 实际实现已移至 components/agricultural-benefit/
 *
 * 本文件为向后兼容保留，从 components 目录重新导出 BenefitRenderer
 */

(function() {
    const script = document.createElement('script');
    script.src = 'components/agricultural-benefit/benefit-renderer.js';
    document.write('<script src="components/agricultural-benefit/benefit-renderer.js"><\/script>');
})();
