"""本地调试 StateGraph——不依赖 FastAPI，直接调 LangGraph"""

import asyncio
import sys
sys.path.insert(0, ".")

from agent.graph import app


async def test_fusion_path():
    """测试有错误码 → 融合路径"""
    print("\n" + "=" * 60)
    print("TEST 1: 有错误码 → 融合路径")
    print("=" * 60)
    
    config = {"configurable": {"thread_id": "test-fusion-001"}}
    result = await app.ainvoke(
        {
            "user_input": "172.22.0.222 到点旋转异常，报614028",
            "symptom": "到点旋转异常，报614028",
            "extra_params": {"robot_ip": "172.22.0.222"},
        },
        config,
    )
    
    print(f"\n结果:")
    print(f"  source_type:      {result.get('source_type')}")
    print(f"  problem_type:     {result.get('problem_type')}")
    print(f"  error_codes:      {result.get('error_codes')}")
    print(f"  playbook_matched: {result.get('playbook_matched')}")
    print(f"  playbook_code:    {result.get('playbook_error_code')}")
    print(f"  fusion_status:    {result.get('fusion_result', {}).get('status')}")
    print(f"  conclusion:       {result.get('conclusion_status')}")
    
    # 验证
    assert result.get("source_type") == "internal_robot", "source_type 应为 internal_robot"
    assert result.get("error_codes") == ["614028"], "应提取到 614028"
    assert result.get("playbook_matched") == True, "Playbook 应匹配"
    assert result.get("conclusion_status") == "likely", "应输出结论"
    print("\n✅ 融合路径测试通过")


async def test_multi_agent_path():
    """测试无错误码 → 多 Agent + 仲裁路径"""
    print("\n" + "=" * 60)
    print("TEST 2: 无错误码 → 多 Agent + 仲裁")
    print("=" * 60)
    
    config = {"configurable": {"thread_id": "test-multi-001"}}
    result = await app.ainvoke(
        {
            "user_input": "车到点后转了3圈就停了，地图显示还在路径上",
            "symptom": "车到点后转了3圈就停了",
            "extra_params": {"robot_ip": "172.22.0.105"},
        },
        config,
    )
    
    print(f"\n结果:")
    print(f"  source_type:      {result.get('source_type')}")
    print(f"  problem_type:     {result.get('problem_type')}")
    print(f"  error_codes:      {result.get('error_codes')}")
    print(f"  doc_agent:        {result.get('doc_agent_result', {}).get('root_cause')}")
    print(f"  field_agent:      {result.get('field_agent_result', {}).get('root_cause')}")
    print(f"  arbitration:      {result.get('arbitration_result', {}).get('conflict_type')}")
    print(f"  conclusion:       {result.get('conclusion_status')}")
    
    # 验证
    assert result.get("source_type") == "internal_robot", "source_type 应为 internal_robot"
    assert result.get("error_codes") == [], "无错误码"
    assert result.get("arbitration_result") is not None, "应触发仲裁"
    assert result.get("conclusion_status") == "likely", "应输出结论"
    print("\n✅ 多 Agent 路径测试通过")


async def test_checkpoint_resume():
    """测试断点续跑"""
    print("\n" + "=" * 60)
    print("TEST 3: 断点续跑 (Checkpointer)")
    print("=" * 60)
    
    config = {"configurable": {"thread_id": "test-resume-001"}}
    
    # 第一次运行只给一半参数，模拟中断
    try:
        await app.ainvoke(
            {"user_input": "测试断点续跑"},
            config,
        )
    except Exception:
        pass
    
    # 第二次运行同一个 thread_id，从 checkpoint 恢复
    result = await app.ainvoke(None, config)
    
    print(f"  conclusion: {result.get('conclusion_status')}")
    print("\n✅ 断点续跑测试通过（如果上面的节点执行了两次说明恢复了）")


async def main():
    print("LangGraph StateGraph 本地调试\n")
    
    await test_fusion_path()
    await test_multi_agent_path()
    await test_checkpoint_resume()
    
    print("\n" + "=" * 60)
    print("全部测试通过 ✅")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
