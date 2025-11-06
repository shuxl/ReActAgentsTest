"""
复诊管理数据库表CRUD独立测试
直接测试appointments表的增删改查操作，不通过智能体
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.database import get_db_pool
from utils.logging_config import setup_logging

# 设置统一的日志配置
setup_logging()


async def ensure_appointment_table_exists(pool):
    """
    确保appointments表存在且结构正确
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # 检查表是否存在
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'appointments'
                    )
                """)
                table_exists = await cur.fetchone()
                
                if not table_exists or not table_exists.get('exists'):
                    print("正在创建appointments表...")
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS appointments (
                            id SERIAL PRIMARY KEY,
                            user_id VARCHAR(255) NOT NULL,
                            department VARCHAR(255) NOT NULL,
                            doctor_id VARCHAR(255),
                            doctor_name VARCHAR(255),
                            appointment_date TIMESTAMP NOT NULL,
                            status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled')),
                            notes TEXT,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    print("✓ 表创建成功")
                    
                    # 创建索引
                    indexes = [
                        "CREATE INDEX IF NOT EXISTS idx_appointments_user_id ON appointments(user_id)",
                        "CREATE INDEX IF NOT EXISTS idx_appointments_appointment_date ON appointments(appointment_date)",
                        "CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status)",
                        "CREATE INDEX IF NOT EXISTS idx_appointments_user_status ON appointments(user_id, status)"
                    ]
                    for index_sql in indexes:
                        try:
                            await cur.execute(index_sql)
                        except Exception as e:
                            print(f"⚠ 索引创建警告: {str(e)}")
                else:
                    print("✓ 表已存在，验证表结构...")
                    # 验证表结构
                    await cur.execute("""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_name = 'appointments'
                        ORDER BY ordinal_position
                    """)
                    columns = await cur.fetchall()
                    print(f"  表字段数量: {len(columns)}")
                    for col in columns:
                        print(f"    - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
                
    except Exception as e:
        print(f"✗ 表结构检查/创建失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


async def cleanup_test_data(pool, user_id: str):
    """
    清理测试数据
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    DELETE FROM appointments 
                    WHERE user_id = %s
                """, (user_id,))
                deleted_count = cur.rowcount
                print(f"✓ 清理测试数据: 删除 {deleted_count} 条记录")
    except Exception as e:
        print(f"⚠ 清理测试数据时出现警告: {str(e)}")


async def test_create(pool, user_id: str):
    """
    测试CREATE操作
    """
    print("\n" + "=" * 60)
    print("测试1: CREATE操作 - 插入预约记录")
    print("-" * 60)
    
    try:
        # 测试数据
        test_cases = [
            {
                "department": "心内科",
                "doctor_id": "doc001",
                "doctor_name": "张医生",
                "appointment_date": datetime.now() + timedelta(days=1),
                "status": "pending",
                "notes": "首次复诊"
            },
            {
                "department": "骨科",
                "doctor_id": None,
                "doctor_name": "李医生",
                "appointment_date": datetime.now() + timedelta(days=2),
                "status": "pending",
                "notes": None
            },
            {
                "department": "眼科",
                "doctor_id": "doc003",
                "doctor_name": None,
                "appointment_date": datetime.now() + timedelta(days=3),
                "status": "pending",
                "notes": "常规检查"
            }
        ]
        
        inserted_ids = []
        
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                for idx, test_case in enumerate(test_cases, 1):
                    print(f"\n  插入记录 {idx}:")
                    print(f"    科室: {test_case['department']}")
                    print(f"    医生ID: {test_case['doctor_id']}")
                    print(f"    医生姓名: {test_case['doctor_name']}")
                    print(f"    预约时间: {test_case['appointment_date']}")
                    print(f"    状态: {test_case['status']}")
                    print(f"    备注: {test_case['notes']}")
                    
                    await cur.execute("""
                        INSERT INTO appointments 
                        (user_id, department, doctor_id, doctor_name, appointment_date, status, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (user_id, test_case['department'], test_case['doctor_id'], 
                          test_case['doctor_name'], test_case['appointment_date'], 
                          test_case['status'], test_case['notes']))
                    
                    result = await cur.fetchone()
                    appointment_id = result['id'] if result else None
                    inserted_ids.append(appointment_id)
                    
                    print(f"    ✓ 插入成功，ID: {appointment_id}")
                    
                    # 验证插入
                    await cur.execute("""
                        SELECT id, user_id, department, doctor_id, doctor_name, appointment_date, status, notes
                        FROM appointments
                        WHERE id = %s
                    """, (appointment_id,))
                    verify_row = await cur.fetchone()
                    
                    if verify_row:
                        print(f"    ✓ 验证成功: 查询到记录")
                        print(f"      user_id={verify_row['user_id']}, department={verify_row['department']}")
                    else:
                        print(f"    ✗ 验证失败: 插入后无法查询到记录")
                        return False
        
        print(f"\n✓ 测试1通过: 成功插入 {len(inserted_ids)} 条记录")
        return inserted_ids
        
    except Exception as e:
        print(f"\n✗ 测试1失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


async def test_read(pool, user_id: str):
    """
    测试READ操作
    """
    print("\n" + "=" * 60)
    print("测试2: READ操作 - 查询预约记录")
    print("-" * 60)
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # 测试2.1: 查询所有记录
                print("\n  测试2.1: 查询所有记录")
                await cur.execute("""
                    SELECT id, department, doctor_id, doctor_name, appointment_date, status, notes, created_at
                    FROM appointments
                    WHERE user_id = %s
                    ORDER BY appointment_date DESC
                """, (user_id,))
                all_rows = await cur.fetchall()
                print(f"    找到 {len(all_rows)} 条记录")
                if all_rows:
                    for row in all_rows:
                        print(f"      ID={row['id']}, 科室={row['department']}, "
                              f"时间={row['appointment_date']}, 状态={row['status']}")
                    print(f"    ✓ 测试2.1通过")
                else:
                    print(f"    ✗ 测试2.1失败: 未找到记录")
                    return False
                
                # 测试2.2: 按状态查询
                print("\n  测试2.2: 按状态查询（pending）")
                await cur.execute("""
                    SELECT id, department, status
                    FROM appointments
                    WHERE user_id = %s AND status = %s
                """, (user_id, 'pending'))
                pending_rows = await cur.fetchall()
                print(f"    找到 {len(pending_rows)} 条pending状态的记录")
                if pending_rows:
                    print(f"    ✓ 测试2.2通过")
                else:
                    print(f"    ✗ 测试2.2失败: 未找到pending状态的记录")
                    return False
                
                # 测试2.3: 按时间范围查询
                print("\n  测试2.3: 按时间范围查询（未来2天内）")
                start_date = datetime.now()
                end_date = datetime.now() + timedelta(days=2)
                await cur.execute("""
                    SELECT id, department, appointment_date
                    FROM appointments
                    WHERE user_id = %s 
                    AND DATE(appointment_date) >= %s
                    AND DATE(appointment_date) <= %s
                """, (user_id, start_date.date(), end_date.date()))
                date_range_rows = await cur.fetchall()
                print(f"    找到 {len(date_range_rows)} 条记录（时间范围: {start_date.date()} 至 {end_date.date()}）")
                if date_range_rows:
                    print(f"    ✓ 测试2.3通过")
                else:
                    print(f"    ✗ 测试2.3失败: 未找到指定时间范围的记录")
                    return False
        
        print(f"\n✓ 测试2通过: 所有查询操作成功")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试2失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_update(pool, user_id: str, appointment_ids: list):
    """
    测试UPDATE操作
    """
    print("\n" + "=" * 60)
    print("测试3: UPDATE操作 - 更新预约记录")
    print("-" * 60)
    
    if not appointment_ids:
        print("  跳过测试: 没有可更新的记录")
        return False
    
    try:
        appointment_id = appointment_ids[0]  # 使用第一条记录进行测试
        
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # 测试3.1: 更新状态
                print(f"\n  测试3.1: 更新状态（ID={appointment_id}）")
                await cur.execute("""
                    UPDATE appointments
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, ('completed', appointment_id, user_id))
                
                # 验证更新
                await cur.execute("""
                    SELECT id, status FROM appointments WHERE id = %s AND user_id = %s
                """, (appointment_id, user_id))
                verify_row = await cur.fetchone()
                
                if verify_row and verify_row['status'] == 'completed':
                    print(f"    ✓ 状态更新成功: {verify_row['status']}")
                else:
                    print(f"    ✗ 状态更新失败")
                    return False
                
                # 测试3.2: 更新多个字段
                print(f"\n  测试3.2: 更新多个字段（ID={appointment_id}）")
                new_department = "心内科（已更新）"
                new_notes = "已更新备注"
                await cur.execute("""
                    UPDATE appointments
                    SET department = %s, notes = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (new_department, new_notes, appointment_id, user_id))
                
                # 验证更新
                await cur.execute("""
                    SELECT id, department, notes FROM appointments WHERE id = %s AND user_id = %s
                """, (appointment_id, user_id))
                verify_row = await cur.fetchone()
                
                if verify_row and verify_row['department'] == new_department and verify_row['notes'] == new_notes:
                    print(f"    ✓ 多字段更新成功")
                    print(f"      department={verify_row['department']}, notes={verify_row['notes']}")
                else:
                    print(f"    ✗ 多字段更新失败")
                    return False
                
                # 测试3.3: 更新预约时间
                print(f"\n  测试3.3: 更新预约时间（ID={appointment_id}）")
                new_appointment_date = datetime.now() + timedelta(days=5)
                await cur.execute("""
                    UPDATE appointments
                    SET appointment_date = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (new_appointment_date, appointment_id, user_id))
                
                # 验证更新
                await cur.execute("""
                    SELECT id, appointment_date FROM appointments WHERE id = %s AND user_id = %s
                """, (appointment_id, user_id))
                verify_row = await cur.fetchone()
                
                if verify_row:
                    updated_date = verify_row['appointment_date']
                    if abs((updated_date - new_appointment_date).total_seconds()) < 60:  # 允许1分钟误差
                        print(f"    ✓ 预约时间更新成功: {updated_date}")
                    else:
                        print(f"    ✗ 预约时间更新失败: 期望={new_appointment_date}, 实际={updated_date}")
                        return False
                else:
                    print(f"    ✗ 预约时间更新失败: 无法查询到记录")
                    return False
        
        print(f"\n✓ 测试3通过: 所有更新操作成功")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试3失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_delete(pool, user_id: str, appointment_ids: list):
    """
    测试DELETE操作
    """
    print("\n" + "=" * 60)
    print("测试4: DELETE操作 - 删除预约记录")
    print("-" * 60)
    
    if len(appointment_ids) < 2:
        print("  跳过测试: 记录数量不足（需要至少2条记录）")
        return False
    
    try:
        # 删除第二条记录（保留第一条用于其他测试）
        delete_id = appointment_ids[1]
        
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # 先确认记录存在
                await cur.execute("""
                    SELECT id FROM appointments WHERE id = %s AND user_id = %s
                """, (delete_id, user_id))
                before_delete = await cur.fetchone()
                
                if not before_delete:
                    print(f"    ✗ 测试4失败: 记录不存在（ID={delete_id}）")
                    return False
                
                print(f"\n  删除记录（ID={delete_id}）")
                await cur.execute("""
                    DELETE FROM appointments
                    WHERE id = %s AND user_id = %s
                """, (delete_id, user_id))
                
                # 验证删除
                await cur.execute("""
                    SELECT id FROM appointments WHERE id = %s AND user_id = %s
                """, (delete_id, user_id))
                after_delete = await cur.fetchone()
                
                if not after_delete:
                    print(f"    ✓ 删除成功")
                else:
                    print(f"    ✗ 删除失败: 记录仍然存在")
                    return False
                
                # 验证其他记录仍然存在
                await cur.execute("""
                    SELECT COUNT(*) as count FROM appointments WHERE user_id = %s
                """, (user_id,))
                remaining_count = await cur.fetchone()
                expected_count = len(appointment_ids) - 1
                
                if remaining_count and remaining_count['count'] == expected_count:
                    print(f"    ✓ 验证通过: 剩余记录数={remaining_count['count']}（期望={expected_count}）")
                else:
                    print(f"    ✗ 验证失败: 剩余记录数={remaining_count['count'] if remaining_count else 0}（期望={expected_count}）")
                    return False
        
        print(f"\n✓ 测试4通过: 删除操作成功")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试4失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_constraints(pool, user_id: str):
    """
    测试约束（CHECK约束、外键约束等）
    """
    print("\n" + "=" * 60)
    print("测试5: 约束测试 - 验证数据约束")
    print("-" * 60)
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # 测试5.1: 测试无效状态值
                print("\n  测试5.1: 测试无效状态值")
                try:
                    await cur.execute("""
                        INSERT INTO appointments 
                        (user_id, department, appointment_date, status)
                        VALUES (%s, %s, %s, %s)
                    """, (user_id, "测试科室", datetime.now() + timedelta(days=1), "invalid_status"))
                    print(f"    ✗ 测试5.1失败: 应该拒绝无效状态值")
                    return False
                except Exception as e:
                    if "check constraint" in str(e).lower() or "invalid" in str(e).lower():
                        print(f"    ✓ 测试5.1通过: 正确拒绝了无效状态值")
                    else:
                        print(f"    ⚠ 测试5.1: 出现其他错误: {str(e)}")
                
                # 测试5.2: 测试必填字段（department）
                print("\n  测试5.2: 测试必填字段（department为NULL）")
                try:
                    await cur.execute("""
                        INSERT INTO appointments 
                        (user_id, department, appointment_date)
                        VALUES (%s, %s, %s)
                    """, (user_id, None, datetime.now() + timedelta(days=1)))
                    print(f"    ✗ 测试5.2失败: 应该拒绝NULL department")
                    return False
                except Exception as e:
                    if "not null" in str(e).lower() or "null" in str(e).lower():
                        print(f"    ✓ 测试5.2通过: 正确拒绝了NULL department")
                    else:
                        print(f"    ⚠ 测试5.2: 出现其他错误: {str(e)}")
                
                # 测试5.3: 测试必填字段（appointment_date）
                print("\n  测试5.3: 测试必填字段（appointment_date为NULL）")
                try:
                    await cur.execute("""
                        INSERT INTO appointments 
                        (user_id, department, appointment_date)
                        VALUES (%s, %s, %s)
                    """, (user_id, "测试科室", None))
                    print(f"    ✗ 测试5.3失败: 应该拒绝NULL appointment_date")
                    return False
                except Exception as e:
                    if "not null" in str(e).lower() or "null" in str(e).lower():
                        print(f"    ✓ 测试5.3通过: 正确拒绝了NULL appointment_date")
                    else:
                        print(f"    ⚠ 测试5.3: 出现其他错误: {str(e)}")
        
        print(f"\n✓ 测试5通过: 所有约束测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试5失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_appointment_table_crud():
    """
    复诊管理数据库表CRUD完整测试
    """
    print("=" * 60)
    print("复诊管理数据库表CRUD独立测试")
    print("=" * 60)
    
    # 初始化数据库连接池
    db_pool = get_db_pool()
    await db_pool.create_pool()
    
    # 确保表结构正确
    await ensure_appointment_table_exists(db_pool.pool)
    
    # 测试用户ID
    user_id = "test_user_crud_001"
    
    # 测试开始前清理旧数据
    print("\n[清理] 测试前清理旧数据")
    print("-" * 60)
    await cleanup_test_data(db_pool.pool, user_id)
    
    # 执行测试
    test_results = []
    
    # 测试1: CREATE
    inserted_ids = await test_create(db_pool.pool, user_id)
    test_results.append(("CREATE", len(inserted_ids) > 0))
    
    if not inserted_ids:
        print("\n✗ CREATE测试失败，停止后续测试")
        await db_pool.close()
        return False
    
    # 测试2: READ
    read_result = await test_read(db_pool.pool, user_id)
    test_results.append(("READ", read_result))
    
    # 测试3: UPDATE
    update_result = await test_update(db_pool.pool, user_id, inserted_ids)
    test_results.append(("UPDATE", update_result))
    
    # 测试4: DELETE
    delete_result = await test_delete(db_pool.pool, user_id, inserted_ids)
    test_results.append(("DELETE", delete_result))
    
    # 测试5: 约束测试
    constraint_result = await test_constraints(db_pool.pool, user_id)
    test_results.append(("CONSTRAINTS", constraint_result))
    
    # 测试结束后清理数据
    # print("\n[清理] 测试后清理数据")
    # print("-" * 60)
    # await cleanup_test_data(db_pool.pool, user_id)
    
    # 清理资源
    await db_pool.close()
    
    # 汇总测试结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    all_passed = True
    for test_name, result in test_results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name:15s}: {status}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有测试通过！")
    else:
        print("✗ 部分测试失败")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_appointment_table_crud())
    sys.exit(0 if success else 1)

