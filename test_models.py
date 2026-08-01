"""验证模型路由——调 one-api 代理"""
import sys, asyncio
sys.path.insert(0, ".")

from models.router import route, MODEL_CONFIG

async def test():
    tests = [
        ("identify_source", "用户说：172.22.0.222 到点后转了3圈就停了。请问这是什么来源？只回答: internal_robot/tb_task/remote_site/local_logs/insufficient_data"),
        ("playbook_fallback", "日志行: 'invalid path node attribute, id=-1'. 这个日志是否等价于 'parse path_node failed'？只答是或否。"),
        ("fuse_simple", "两个Agent得出相同结论吗？AgentA: 相机超时。AgentB: QR消息超时导致定位失败。只答: 一致/上下游/矛盾"),
    ]

    for task, prompt in tests:
        print(f"\n{'='*50}")
        print(f"测试: {task}")
        print(f"模型: {MODEL_CONFIG[task]['model']}")
        print(f"{'='*50}")
        try:
            result = await route(task, [{"role": "user", "content": prompt}])
            print(f"响应: {result['content'][:200]}")
            print(f"模型: {result['model']}")
            print(f"Token: {result['tokens']}")
            print(f"费用: ${result['cost']:.6f}")
        except Exception as e:
            print(f"❌ 失败: {e}")

asyncio.run(test())
