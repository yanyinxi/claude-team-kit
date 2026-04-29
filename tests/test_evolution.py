"""进化系统测试"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.config import EvolutionConfig, TriggerConfig
from evolution.engine import EvolutionEngine


def test_config():
    """测试配置管理"""
    config = EvolutionConfig()
    
    assert config.skill_trigger.min_invocations == 10
    assert config.confirmation.mode == "interactive_first_n"
    
    print("✅ Config test passed")


def test_engine_init():
    """测试引擎初始化"""
    config = EvolutionConfig()
    engine = EvolutionEngine(config)
    
    stats = engine.get_evolution_stats()
    assert isinstance(stats, dict)
    assert "total_evolutions" in stats
    
    print("✅ Engine init test passed")


def test_evolution_stats():
    """测试进化统计"""
    config = EvolutionConfig()
    engine = EvolutionEngine(config)
    
    stats = engine.get_evolution_stats()
    print(f"   Total evolutions: {stats['total_evolutions']}")
    print(f"   Success rate: {stats['success_rate']*100:.1f}%")
    print(f"   Pending confirmations: {stats['pending_confirmations']}")
    
    print("✅ Stats test passed")


def test_skill_evolver():
    """测试 Skill 进化器"""
    from evolution.evolvers.skill_evolver import SkillEvolver
    
    config = EvolutionConfig()
    evolver = SkillEvolver(config)
    
    targets = evolver.get_all_targets()
    print(f"   Found {len(targets)} skills")
    
    if targets:
        analysis = evolver.analyze_performance(targets[0])
        print(f"   Analysis keys: {list(analysis.keys())}")
    
    print("✅ Skill evolver test passed")


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Running Evolution System Tests")
    print("=" * 50)
    
    tests = [
        test_config,
        test_engine_init,
        test_evolution_stats,
        test_skill_evolver,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
