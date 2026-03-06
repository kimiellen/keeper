# ADR-002: Tag 和 Relation 独立成表而非 JSON 数组

**状态**：已接受  
**日期**：2026-03-06  
**决策者**：Keeper 开发团队（基于用户需求）  
**相关文档**：[schema.md](../schema.md)

---

## 背景与问题

在设计 Bookmark 表时，Tag（标签）和 Relation（关联关系）有两种存储方案：

**方案 A**：独立表 + bookmark 中存储 ID 数组
```sql
CREATE TABLE tags (id, name, color, ...);
CREATE TABLE bookmarks (tag_ids TEXT, ...);  -- JSON: [1, 3, 5]
```

**方案 B**：直接存储为 JSON 数组
```sql
CREATE TABLE bookmarks (tags TEXT, ...);  -- JSON: [{"name": "工作", "color": "#3B82F6"}, ...]
```

需要决定：Tag 和 Relation 是否独立成表？

---

## 决策

**Tag 和 Relation 独立成表，bookmark 中存储 ID 数组**

---

## 理由

### 1. UI 交互需求（核心驱动因素）

**用户需求（原文）**：
> "标签和关联都独立管理增删改查。在插件中我有专门针对 tags 和 relation 的增删改查页面。在创建书签记录的时候 tags 的输入界面和 relation 的输入界面，只提供多选框。"

**独立表的优势**：
```typescript
// 标签管理页面：GET /api/v1/tags
[
  { id: 1, name: "工作", color: "#3B82F6", usageCount: 25 },
  { id: 2, name: "个人", color: "#10B981", usageCount: 18 }
]

// 创建书签时：多选框直接使用
<Checkbox v-for="tag in allTags" :key="tag.id" :value="tag.id">
  {{ tag.name }}
</Checkbox>
```

**JSON 数组的问题**：
- 无法直接获取"所有标签列表"
- 需要扫描所有 bookmark 并去重
- 标签重命名需要更新所有 bookmark
- 无法统计标签使用次数

### 2. 数据一致性

**场景 1：标签重命名**

**独立表**：
```sql
-- 修改一次，所有 bookmark 自动生效
UPDATE tags SET name = '工作相关' WHERE id = 1;
```

**JSON 数组**：
```python
# 需要扫描并更新所有 bookmark
for bookmark in all_bookmarks:
    for tag in bookmark.tags:
        if tag['name'] == '工作':
            tag['name'] = '工作相关'
    update_bookmark(bookmark)
```

**场景 2：标签删除**

**独立表**：
```python
# 1. 删除 tag
DELETE FROM tags WHERE id = 1;

# 2. 清理 bookmark 中的引用（应用层级联）
UPDATE bookmarks 
SET tag_ids = remove_from_json_array(tag_ids, 1)
WHERE json_contains(tag_ids, 1);
```

**JSON 数组**：
```python
# 同样需要扫描所有 bookmark
# 但无法确保删除后新 bookmark 不再使用该标签
```

### 3. 查询效率

**查询"所有标签"**：

**独立表**：
```sql
SELECT * FROM tags;  -- O(n) n=标签数量（通常 < 100）
```

**JSON 数组**：
```python
# 需要扫描所有 bookmark 并去重
all_tags = set()
for bookmark in bookmarks:  # O(m) m=书签数量（可能 > 1000）
    all_tags.update(bookmark.tags)
```

**查询"包含特定标签的书签"**：

**独立表**：
```sql
SELECT * FROM bookmarks 
WHERE json_each.value = 1  -- 可使用索引
AND json_each.key IN (SELECT key FROM json_each(tag_ids));
```

**JSON 数组**：
```python
# 同样需要扫描 JSON，但无法引用独立的标签记录
```

### 4. 统计功能

**独立表支持的统计**：
```sql
-- 每个标签的使用次数
SELECT t.name, COUNT(*) as usage_count
FROM tags t
LEFT JOIN bookmarks b ON json_contains(b.tag_ids, t.id)
GROUP BY t.id;

-- 未使用的标签
SELECT * FROM tags
WHERE id NOT IN (
    SELECT DISTINCT json_each.value FROM bookmarks, json_each(bookmarks.tag_ids)
);
```

**JSON 数组的困难**：
- 无法直接统计
- 需要完整扫描所有 bookmark

---

## 权衡

### 独立表的代价

| 代价 | 影响程度 | 缓解措施 |
|------|---------|---------|
| 级联删除需手动实现 | 中 | 应用层处理，单用户场景可接受 |
| JOIN 查询复杂度 | 低 | SQLite JSON 函数支持良好 |
| 额外的表维护 | 低 | 表结构简单（3-4 字段） |

### JSON 数组的优势（对本项目不重要）

| JSON 优势 | 是否需要 |
|----------|---------|
| 无需 JOIN 查询 | ❌ 查询简单，JOIN 成本低 |
| 数据紧凑存储 | ❌ 数据量小（< 10MB） |
| 读取性能高 | ❌ 独立表已足够快 |

---

## 决策后果

### 正面影响

1. **UI 开发简化**：
   - 标签管理页面直接 CRUD tags 表
   - 创建书签时，直接获取所有标签列表
   - 多选框绑定简单

2. **数据一致性保证**：
   - 标签修改一次，所有 bookmark 生效
   - 删除标签时可清理所有引用

3. **扩展性强**：
   - 可轻松添加 `tag.description`（标签描述）
   - 可添加 `tag.icon`（标签图标）
   - 可统计标签使用情况

4. **迁移友好**：
   - 未来如需迁移到 PostgreSQL，结构无需调整
   - 符合关系型数据库范式

### 负面影响（及缓解措施）

1. **级联删除需手动实现**：
   - **影响**：删除 tag 时需扫描所有 bookmark
   - **缓解**：单用户场景，数据量小（< 1000 条），性能可接受

2. **JOIN 查询复杂度**：
   - **影响**：查询"包含特定标签的书签"需 JSON 函数
   - **缓解**：SQLite 的 `json_each()` 函数性能良好

---

## 实现细节

### 表结构

```sql
-- Tag 表
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6B7280',
    created_at TEXT NOT NULL
);

-- Bookmark 表（部分字段）
CREATE TABLE bookmarks (
    id TEXT PRIMARY KEY,
    tag_ids TEXT NOT NULL DEFAULT '[]',  -- JSON: [1, 3, 5]
    ...
);
```

### 级联删除实现

```python
def delete_tag(tag_id: int):
    """删除标签并清理所有 bookmark 中的引用"""
    async with get_db() as db:
        # 1. 获取所有包含该 tag_id 的 bookmark
        cursor = await db.execute(
            "SELECT id, tag_ids FROM bookmarks"
        )
        bookmarks = await cursor.fetchall()
        
        # 2. 更新每个 bookmark，移除 tag_id
        for bookmark_id, tag_ids_json in bookmarks:
            tag_ids = json.loads(tag_ids_json)
            if tag_id in tag_ids:
                tag_ids.remove(tag_id)
                await db.execute(
                    "UPDATE bookmarks SET tag_ids = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(tag_ids), datetime.now().isoformat(), bookmark_id)
                )
        
        # 3. 删除 tag
        await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        await db.commit()
```

### API 设计

```python
# 标签管理 API
@router.get("/tags")
async def list_tags():
    """获取所有标签（含使用统计）"""
    return await tag_service.get_all_with_usage_count()

@router.post("/tags")
async def create_tag(name: str, color: str):
    """创建标签"""
    return await tag_service.create(name, color)

@router.put("/tags/{tag_id}")
async def update_tag(tag_id: int, name: str, color: str):
    """更新标签（自动影响所有 bookmark）"""
    return await tag_service.update(tag_id, name, color)

@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: int):
    """删除标签（自动清理 bookmark 引用）"""
    return await tag_service.delete(tag_id)
```

---

## 替代方案

### 方案 A：完全范式化（多对多关系表）

```sql
CREATE TABLE tags (id, name, color);
CREATE TABLE bookmarks (id, name, ...);
CREATE TABLE bookmark_tags (bookmark_id, tag_id);  -- 关系表
```

**优势**：
- 标准的关系型设计
- JOIN 查询简单

**劣势**：
- 增加表数量（复杂度上升）
- 查询需 JOIN 三张表
- 对单用户场景过度设计

**拒绝理由**：SQLite 中 JSON 数组性能已足够，无需额外关系表。

---

### 方案 B：JSON 数组存储完整对象

```sql
CREATE TABLE bookmarks (
    tags TEXT  -- JSON: [{"id": 1, "name": "工作", "color": "#3B82F6"}, ...]
);
```

**优势**：
- 无需 JOIN
- 读取时数据完整

**劣势**：
- 数据冗余（每个 bookmark 都存完整 tag 信息）
- 标签修改需更新所有 bookmark
- 无法保证数据一致性

**拒绝理由**：违反数据库范式，数据一致性无法保证。

---

## 验证与监控

### 验证指标

- [ ] **级联删除**：删除 tag 后，所有 bookmark 的 tag_ids 已更新
- [ ] **性能**：删除 tag（含级联）耗时 < 100ms（1000 条 bookmark）
- [ ] **UI 体验**：标签管理页面加载 < 50ms

### 监控计划

- 记录级联删除的扫描记录数
- 监控标签列表查询耗时
- 用户反馈标签管理体验

---

## 相关决策

- [ADR-001: SQLite 数据库选择](./001-sqlite-over-postgresql.md)
- [ADR-004: 四层安全防护](./004-four-layer-security.md)

---

## 参考资料

- [SQLite JSON 函数](https://www.sqlite.org/json1.html)
- [数据库范式化](https://en.wikipedia.org/wiki/Database_normalization)
- [Bitwarden 数据模型](https://github.com/bitwarden/server/tree/master/src/Core/Models)

---

**决策状态**：✅ 已实施（Phase 1）  
**下次审查**：Phase 3（UI 实现阶段验证交互体验）
