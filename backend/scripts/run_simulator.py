"""
数据模拟器 - 命令行版
支持参数化生成不同年代、不同类型的遗迹数据和水文重建数据

用法:
    python -m scripts.run_simulator                     # 默认生成300处遗迹，全朝代全类型
    python -m scripts.run_simulator --sites 100         # 100处
    python -m scripts.run_simulator --dynasty 唐        # 仅唐代
    python -m scripts.run_simulator --type 渠,堰        # 仅渠和堰
    python -m scripts.run_simulator --seed 123          # 固定随机种子
    python -m scripts.run_simulator --no-hydrology      # 仅导入遗迹，不生成水文
    python -m scripts.run_simulator --hydro-only        # 仅生成水文数据
    python -m scripts.run_simulator --list-dynasties    # 列出所有朝代
"""
import sys
import os
import argparse
import random
import hashlib
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 延迟导入 common 模块（仅数据库写入时需要 pydantic_settings 等依赖）
# REGIONS 直接内联以避免依赖 hydraulic_params
REGIONS = [
    '中原地区', '关中地区', '江南地区', '巴蜀地区',
    '岭南地区', '江淮地区', '山东地区', '河北地区',
    '河东地区', '河西地区', '辽东地区', '滇黔地区',
]


# ========== 朝代定义 ==========
DYNASTIES = [
    {"id": 1, "name": "春秋", "start_year": -770, "end_year": -476, "order": 1, "weight": 0.03},
    {"id": 2, "name": "战国", "start_year": -475, "end_year": -221, "order": 2, "weight": 0.04},
    {"id": 3, "name": "秦", "start_year": -221, "end_year": -207, "order": 3, "weight": 0.03},
    {"id": 4, "name": "西汉", "start_year": -206, "end_year": 8, "order": 4, "weight": 0.08},
    {"id": 5, "name": "东汉", "start_year": 25, "end_year": 220, "order": 5, "weight": 0.06},
    {"id": 6, "name": "三国", "start_year": 220, "end_year": 280, "order": 6, "weight": 0.04},
    {"id": 7, "name": "西晋", "start_year": 265, "end_year": 316, "order": 7, "weight": 0.03},
    {"id": 8, "name": "东晋", "start_year": 317, "end_year": 420, "order": 8, "weight": 0.04},
    {"id": 9, "name": "南北朝", "start_year": 420, "end_year": 589, "order": 9, "weight": 0.05},
    {"id": 10, "name": "隋", "start_year": 581, "end_year": 618, "order": 10, "weight": 0.04},
    {"id": 11, "name": "唐", "start_year": 618, "end_year": 907, "order": 11, "weight": 0.12},
    {"id": 12, "name": "五代", "start_year": 907, "end_year": 960, "order": 12, "weight": 0.04},
    {"id": 13, "name": "北宋", "start_year": 960, "end_year": 1127, "order": 13, "weight": 0.10},
    {"id": 14, "name": "南宋", "start_year": 1127, "end_year": 1279, "order": 14, "weight": 0.08},
    {"id": 15, "name": "元", "start_year": 1271, "end_year": 1368, "order": 15, "weight": 0.06},
    {"id": 16, "name": "明", "start_year": 1368, "end_year": 1644, "order": 16, "weight": 0.12},
    {"id": 17, "name": "清", "start_year": 1644, "end_year": 1912, "order": 17, "weight": 0.04},
]

# 区域经纬度中心
REGION_CENTERS = {
    '中原地区': (34.5, 113.5),
    '关中地区': (34.3, 108.9),
    '江南地区': (31.2, 120.5),
    '巴蜀地区': (30.7, 104.1),
    '岭南地区': (23.1, 113.3),
    '江淮地区': (32.0, 118.8),
    '山东地区': (36.7, 117.0),
    '河北地区': (38.0, 115.5),
    '河东地区': (37.5, 112.5),
    '河西地区': (39.0, 100.5),
    '辽东地区': (41.8, 123.4),
    '滇黔地区': (26.6, 106.6),
}

SITE_TYPES = ['渠', '堰', '陂', '塘', '井']
TYPE_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]

STATUS_OPTIONS = ['完好', '部分损毁', '完全废弃']
STATUS_WEIGHTS = [0.25, 0.50, 0.25]


# ========== 名字生成 ==========
SITE_NAME_PREFIXES = [
    '龙', '凤', '金', '玉', '永', '安', '太', '平', '万', '福',
    '清', '白', '青', '翠', '古', '灵', '神', '圣', '文', '武',
]
SITE_NAME_SUFFIXES = {
    '渠': ['渠', '灌渠', '引水渠', '通济渠', '惠民渠'],
    '堰': ['堰', '大坝', '分水堰', '溢流堰', '石堰'],
    '陂': ['陂', '湖陂', '蓄水陂', '官陂', '民陂'],
    '塘': ['塘', '水塘', '山塘', '平塘', '陂塘'],
    '井': ['井', '古井', '泉井', '水井', '八卦井'],
}


def generate_site_name(site_type):
    prefix = random.choice(SITE_NAME_PREFIXES)
    suffix = random.choice(SITE_NAME_SUFFIXES[site_type])
    return f"{prefix}{suffix}"


def weighted_choice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


# ========== 遗迹生成 ==========
def generate_sites(count, dynasty_filter=None, type_filter=None, seed=42):
    """生成遗迹数据"""
    random.seed(seed)

    # 应用朝代过滤
    available_dynasties = DYNASTIES
    if dynasty_filter and dynasty_filter.lower() != 'all':
        filtered = [d for d in DYNASTIES
                    if d['name'] == dynasty_filter
                    or d['name'].startswith(dynasty_filter)]
        if filtered:
            available_dynasties = filtered

    # 应用类型过滤
    available_types = SITE_TYPES
    available_weights = TYPE_WEIGHTS
    if type_filter and type_filter.lower() != 'all':
        selected_types = [t.strip() for t in type_filter.split(',') if t.strip() in SITE_TYPES]
        if selected_types:
            available_types = selected_types
            available_weights = [1.0 / len(selected_types)] * len(selected_types)

    sites = []
    dynasty_weights = [d['weight'] for d in available_dynasties]

    for i in range(count):
        dynasty = weighted_choice(available_dynasties, dynasty_weights)
        site_type = weighted_choice(available_types, available_weights)
        status = weighted_choice(STATUS_OPTIONS, STATUS_WEIGHTS)

        # 区域选择：基于名字确定性哈希
        name = generate_site_name(site_type)
        region_idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(REGIONS)
        region = REGIONS[region_idx]
        center_lat, center_lon = REGION_CENTERS.get(region, (34.0, 110.0))

        # 经纬度偏移
        lon = center_lon + (random.random() - 0.5) * 3.0
        lat = center_lat + (random.random() - 0.5) * 2.5

        # 结构参数
        irrigation_area = max(5.0, random.lognormvariate(5.0, 1.2))

        if site_type == '井':
            dam_height = None
            canal_length = None
        else:
            dam_height = max(0.5, random.gauss(
                {'渠': 3.5, '堰': 10.0, '陂': 12.0, '塘': 5.0}[site_type], 3.0
            ))
            dam_height = round(dam_height, 1)

            if site_type == '渠':
                canal_length = max(5.0, random.gauss(80, 50))
                canal_length = round(canal_length, 1)
            else:
                canal_length = None

        description = (f"{dynasty['name']}代{site_type}类水利工程，"
                       f"位于{region}，主要用于农业灌溉和防洪。")

        sites.append({
            'name': name,
            'dynasty': dynasty['name'],
            'dynasty_order': dynasty['order'],
            'longitude': round(lon, 6),
            'latitude': round(lat, 6),
            'site_type': site_type,
            'dam_height': dam_height,
            'canal_length': canal_length,
            'irrigation_area': round(irrigation_area, 1),
            'preservation_status': status,
            'description': description,
        })

    return sites, available_dynasties


# ========== 水文数据生成 ==========
def generate_hydrology(dynasties=None, seed=42):
    """生成每10年分辨率的水文重建数据"""
    random.seed(seed)
    np_seed = seed
    try:
        import numpy as np
        np.random.seed(np_seed)
        has_numpy = True
    except ImportError:
        has_numpy = False

    if dynasties is None:
        dynasties = DYNASTIES

    records = []
    all_years = []

    # 生成所有需要的年份
    for dyn in dynasties:
        start = max(dyn['start_year'] - (dyn['start_year'] % 10), -770)
        end = min(dyn['end_year'] + 10, 1912)
        year = start
        while year <= end:
            if -770 <= year <= 1912:
                all_years.append((year, dyn['name']))
            year += 10

    # 去重
    seen = set()
    unique_years = []
    for y, d in all_years:
        if y not in seen:
            seen.add(y)
            unique_years.append((y, d))
    unique_years.sort()

    for region in REGIONS:
        # 基准气候参数
        base_rainfall = 700 + random.random() * 500  # 700~1200mm
        base_runoff = 200 + random.random() * 400     # 200~600万m³

        # 长期趋势系数
        if has_numpy:
            trend = np.linspace(-0.1, 0.1, len(unique_years))
            noise_rain = np.random.normal(0, 0.08, len(unique_years))
            noise_runoff = np.random.normal(0, 0.12, len(unique_years))
            noise_temp = np.random.normal(0, 0.5, len(unique_years))
        else:
            trend = [0] * len(unique_years)
            noise_rain = [random.gauss(0, 0.08) for _ in unique_years]
            noise_runoff = [random.gauss(0, 0.12) for _ in unique_years]
            noise_temp = [random.gauss(0, 0.5) for _ in unique_years]

        for i, (year, dyn_name) in enumerate(unique_years):
            rainfall_factor = 1.0 + trend[i] + noise_rain[i]
            runoff_factor = 1.0 + trend[i] * 1.2 + noise_runoff[i]
            temperature = 14.0 + trend[i] * 3 + noise_temp[i]

            rainfall = max(100, base_rainfall * rainfall_factor)
            runoff = max(50, base_runoff * runoff_factor)

            records.append({
                'year': year,
                'region': region,
                'rainfall': round(rainfall, 1),
                'runoff': round(runoff, 1),
                'temperature': round(temperature, 2),
            })

    return records


# ========== 数据库写入 ==========
def insert_to_database(sites, hydrology, dynasties_list):
    """写入PostgreSQL数据库"""
    try:
        from common.database import SessionLocal, init_db
        from common.models import WaterHeritageSite, PaleoHydrologyData, DynastyDict
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point
        from sqlalchemy import text
    except ImportError as e:
        print(f"⚠️  缺少数据库依赖，跳过写入: {e}")
        print(f"   已生成 {len(sites)} 处遗迹，{len(hydrology)} 条水文记录")
        return False

    print("📦 正在写入数据库...")
    init_db()
    db = SessionLocal()

    try:
        # 朝代字典
        print("  → 写入朝代字典...")
        for d in dynasties_list:
            existing = db.query(DynastyDict).filter(DynastyDict.order == d['order']).first()
            if not existing:
                db.add(DynastyDict(
                    id=d['id'], name=d['name'],
                    start_year=d['start_year'], end_year=d['end_year'], order=d['order']
                ))
        db.flush()

        # 遗迹数据
        print(f"  → 写入 {len(sites)} 处遗迹...")
        count = 0
        for s in sites:
            point = Point(s['longitude'], s['latitude'])
            geom = from_shape(point, srid=4326)
            site = WaterHeritageSite(
                name=s['name'], dynasty=s['dynasty'],
                dynasty_order=s['dynasty_order'],
                longitude=s['longitude'], latitude=s['latitude'],
                geom=geom, site_type=s['site_type'],
                dam_height=s['dam_height'], canal_length=s['canal_length'],
                irrigation_area=s['irrigation_area'],
                preservation_status=s['preservation_status'],
                description=s['description'],
            )
            db.add(site)
            count += 1
            if count % 100 == 0:
                db.flush()
                print(f"    · 已写入 {count}/{len(sites)}")

        db.flush()

        # 水文数据
        if hydrology:
            print(f"  → 写入 {len(hydrology)} 条水文记录...")
            count = 0
            for h in hydrology:
                record = PaleoHydrologyData(
                    year=h['year'], region=h['region'],
                    rainfall=h['rainfall'], runoff=h['runoff'],
                    temperature=h['temperature'],
                )
                db.add(record)
                count += 1
                if count % 500 == 0:
                    db.flush()
                    print(f"    · 已写入 {count}/{len(hydrology)}")

        db.commit()
        print(f"\n✅ 写入完成！")
        print(f"   朝代: {len(dynasties_list)} 个")
        print(f"   遗迹: {len(sites)} 处")
        if hydrology:
            print(f"   水文: {len(hydrology)} 条")
        return True

    except Exception as e:
        db.rollback()
        print(f"❌ 写入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


# ========== 作物播种/收获月 ==========
CROP_SEASONS = {
    '粟': {'start': 4, 'end': 9},
    '稻': {'start': 5, 'end': 10},
    '麦': {'start': 10, 'end': 6},
    '黍': {'start': 4, 'end': 9},
    '豆': {'start': 6, 'end': 11},
}


def _publish_event(event_name: str, payload: dict = None):
    """模拟事件发布（无MQ依赖时降级为日志记录）"""
    try:
        from common.events import publish_event
        publish_event(event_name, payload or {})
        print(f"  📡 已发布事件: {event_name}")
    except (ImportError, Exception):
        print(f"  📡 [模拟] 事件: {event_name} | payload={payload or {}}")


def _generate_polygon_24pts(cx: float, cy: float, radius_km: float, seed: int = 42) -> str:
    """生成24点不规则多边形的WKT字符串"""
    random.seed(seed)
    pts = []
    for i in range(24):
        angle = (i / 24) * 2 * math.pi
        r_factor = 0.75 + random.random() * 0.5
        r = radius_km * r_factor
        dlat = (r / 111.0) * math.cos(angle)
        dlon = (r / (111.0 * math.cos(math.radians(cy)))) * math.sin(angle)
        pts.append(f"{cx + dlon:.6f} {cy + dlat:.6f}")
    pts.append(pts[0])
    return f"POLYGON(({', '.join(pts)}))"


def _generate_risk_polygon(cx: float, cy: float, depth_m: float) -> str:
    """根据淹没深度生成风险区多边形"""
    scale = 0.5 + min(depth_m / 3.2, 1.0) * 3.5
    return _generate_polygon_24pts(cx, cy, scale, seed=int(depth_m * 1000))


# ========== 古代作物产量基准 ==========
def insert_ancient_crop_yields(db=None):
    """生成12区域×5作物×17朝代=1020条古代作物产量基准数据"""
    random.seed(42)
    try:
        from common.params.crop_params import BASELINE_YIELDS, CROP_KC, IRRIGATION_YIELD_GAIN_FACTOR
        from common.models import AncientCropYield
        from sqlalchemy.dialects.postgresql import insert
    except ImportError as e:
        print(f"⚠️  缺少依赖，跳过作物产量生成: {e}")
        return False

    need_close = False
    if db is None:
        try:
            from common.database import SessionLocal, init_db
            init_db()
            db = SessionLocal()
            need_close = True
        except ImportError as e:
            print(f"⚠️  缺少数据库依赖: {e}")
            return False

    print("🌾 正在生成古代作物产量基准数据...")
    try:
        records = []
        for region in REGIONS:
            for crop in ['粟', '稻', '麦', '黍', '豆']:
                for dyn in DYNASTIES:
                    dyn_order = dyn['order']
                    baseline = BASELINE_YIELDS.get(region, {}).get(crop, {}).get(dyn_order, 100.0)
                    irr_gain = IRRIGATION_YIELD_GAIN_FACTOR.get(crop, {}).get('by_dynasty', {}).get(dyn_order, 0.25)
                    yield_with_irr = round(baseline * (1 + irr_gain), 4)
                    kc = CROP_KC.get(crop, {})
                    seasons = CROP_SEASONS.get(crop, {'start': 4, 'end': 9})
                    records.append({
                        'region': region,
                        'crop_type': crop,
                        'dynasty_order': dyn_order,
                        'yield_baseline_kg_per_mu': round(baseline, 4),
                        'yield_with_irrigation_kg_per_mu': yield_with_irr,
                        'growing_season_start': seasons['start'],
                        'growing_season_end': seasons['end'],
                        'kc_initial': round(kc.get('initial', 0.35), 3),
                        'kc_mid': round(kc.get('mid', 1.05), 3),
                        'kc_late': round(kc.get('late', 0.55), 3),
                    })

        print(f"  → 共 {len(records)} 条记录 (12×5×17)")
        if records:
            stmt = insert(AncientCropYield).values(records)
            stmt = stmt.on_conflict_do_nothing()
            result = db.execute(stmt)
            db.commit()
            inserted = result.rowcount if hasattr(result, 'rowcount') else '批量'
            print(f"  ✅ UPSERT完成，新增: {inserted} 条")
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ 作物产量写入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if need_close:
            db.close()


# ========== 农业影响评估 ==========
def generate_agriculture_impact_batch(db=None):
    """为已有遗址生成农业影响评估（80%概率生成）"""
    random.seed(42)
    try:
        from common.params.crop_params import (
            BASELINE_YIELDS, FARMER_DENSITY_PER_MU, IRRIGATION_YIELD_GAIN_FACTOR
        )
        from common.models import AgriculturalImpactAssessment, WaterHeritageSite
        from sqlalchemy.dialects.postgresql import insert
    except ImportError as e:
        print(f"⚠️  缺少依赖，跳过农业影响评估: {e}")
        return False

    need_close = False
    if db is None:
        try:
            from common.database import SessionLocal, init_db
            init_db()
            db = SessionLocal()
            need_close = True
        except ImportError as e:
            print(f"⚠️  缺少数据库依赖: {e}")
            return False

    print("🌾 正在生成农业影响评估数据...")
    try:
        sites = db.query(WaterHeritageSite).all()
        print(f"  → 查询到 {len(sites)} 处遗址")

        records = []
        skipped = 0
        for site in sites:
            if random.random() > 0.80:
                skipped += 1
                continue

            region_idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
            region = REGIONS[region_idx]
            crops = ['粟', '稻', '麦', '黍', '豆']
            crop_idx = int(hashlib.md5((site.name + 'crop').encode()).hexdigest(), 16) % len(crops)
            dominant_crop = crops[crop_idx]

            irr_area = site.irrigation_area or 50.0
            area_factor = 0.7 + random.random() * 0.6
            total_area = round(irr_area * area_factor, 4)

            increase_rate_raw = random.gauss(0.42, 0.15)
            increase_rate = round(max(0.15, min(0.75, increase_rate_raw)), 4)

            baseline = BASELINE_YIELDS.get(region, {}).get(dominant_crop, {}).get(
                site.dynasty_order, 100.0
            )
            annual_yield_increase = round(total_area * baseline * increase_rate, 4)

            farmer_density = FARMER_DENSITY_PER_MU.get(region, 5.0)
            farmers_benefited = max(1, int(total_area * farmer_density / 5))

            crop_wue_map = {'粟': 0.85, '稻': 0.65, '麦': 0.95, '黍': 0.80, '豆': 0.70}
            region_wue_adj = {
                '江南地区': 1.1, '巴蜀地区': 1.05, '岭南地区': 1.0, '江淮地区': 1.08,
                '中原地区': 0.95, '关中地区': 0.90, '山东地区': 0.92, '河北地区': 0.88,
                '河东地区': 0.85, '河西地区': 0.80, '辽东地区': 0.82, '滇黔地区': 0.90,
            }
            wue = round(crop_wue_map.get(dominant_crop, 0.8) * region_wue_adj.get(region, 1.0), 4)

            confidence = round(0.60 + random.random() * 0.37, 4)

            radius_km = max(0.3, min(15.0, math.sqrt(irr_area / 50)))
            zone_wkt = _generate_polygon_24pts(
                site.longitude, site.latitude, radius_km, seed=site.id or 42
            )
            try:
                from shapely import wkt
                from geoalchemy2.shape import from_shape
                poly_geom = from_shape(wkt.loads(zone_wkt), srid=4326)
                benefit_geojson = None
            except (ImportError, Exception):
                poly_geom = None
                benefit_geojson = {"type": "Polygon", "radius_km": round(radius_km, 2)}

            records.append({
                'site_id': site.id,
                'dominant_crop': dominant_crop,
                'total_influenced_area_mu': total_area,
                'yield_increase_rate': increase_rate,
                'annual_yield_increase_kg': annual_yield_increase,
                'farmers_benefited_count': farmers_benefited,
                'water_use_efficiency_kg_per_m3': wue,
                'yield_simulation_raw': {
                    'baseline_kg_per_mu': baseline,
                    'dominant_crop': dominant_crop,
                    'irrigation_area_mu': irr_area,
                },
                'benefit_zone_geojson': benefit_geojson,
                'confidence_score': confidence,
            })

        print(f"  → 跳过 {skipped} 处(20%无数据)，生成 {len(records)} 条评估")
        if records:
            stmt = insert(AgriculturalImpactAssessment).values(records)
            stmt = stmt.on_conflict_do_nothing()
            result = db.execute(stmt)
            db.commit()
            inserted = result.rowcount if hasattr(result, 'rowcount') else '批量'
            print(f"  ✅ UPSERT完成，新增: {inserted} 条")

        _publish_event('AGRICULTURE_IMPACT_COMPLETED', {
            'total_sites': len(sites),
            'assessed_count': len(records),
            'batch_mode': True,
        })
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ 农业影响评估写入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if need_close:
            db.close()


# ========== 气候脆弱性评估 ==========
def generate_climate_vulnerability_batch(db=None):
    """生成3情景×4年份=12组合的气候脆弱性评估"""
    random.seed(42)
    try:
        from common.params.climate_params import (
            TEMPERATURE_CHANGE, PRECIPITATION_CHANGE, CLIMATE_SCENARIOS, FUTURE_YEARS,
            VULNERABILITY_MATRIX, get_flood_risk_level, get_drought_level,
            get_vulnerability_level, calc_vulnerability_score,
        )
        from common.models import ClimateVulnerabilityAssessment, WaterHeritageSite
        from sqlalchemy.dialects.postgresql import insert
        from geoalchemy2.shape import from_shape
        from shapely import wkt
    except ImportError as e:
        print(f"⚠️  缺少依赖，跳过气候脆弱性评估: {e}")
        return False

    need_close = False
    if db is None:
        try:
            from common.database import SessionLocal, init_db
            init_db()
            db = SessionLocal()
            need_close = True
        except ImportError as e:
            print(f"⚠️  缺少数据库依赖: {e}")
            return False

    print("🌦️  正在生成气候脆弱性评估数据...")
    try:
        sites = db.query(WaterHeritageSite).all()
        scenarios = ['RCP2.6', 'RCP4.5', 'RCP8.5']
        print(f"  → {len(sites)} 处遗址 × {len(scenarios)}情景 × {len(FUTURE_YEARS)}年份 = {len(sites)*len(scenarios)*len(FUTURE_YEARS)} 条")

        flood_score_map = {'无': 10, '低': 30, '中': 50, '高': 75, '极高': 95}
        drought_score_map = {'无': 10, '低': 30, '中': 50, '高': 75, '极高': 95}
        struct_score_map = {'完好': 15, '部分损毁': 50, '完全废弃': 85}

        records = []
        for site in sites:
            region_idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
            region = REGIONS[region_idx]
            struct_score = struct_score_map.get(site.preservation_status, 50)

            for scenario in scenarios:
                for year in FUTURE_YEARS:
                    temp_change = TEMPERATURE_CHANGE.get(scenario, {}).get(year, 0)
                    precip_data = PRECIPITATION_CHANGE.get(scenario, {}).get(year, {})
                    avg_precip = sum(precip_data.values()) / max(1, len(precip_data)) if precip_data else 0

                    if scenario == 'RCP8.5':
                        max_depth = {2030: 0.8, 2050: 1.6, 2070: 2.5, 2100: 3.2}[year]
                        min_spei = {2030: -0.9, 2050: -1.4, 2070: -1.9, 2100: -2.4}[year]
                    elif scenario == 'RCP4.5':
                        max_depth = {2030: 0.5, 2050: 1.0, 2070: 1.6, 2100: 2.1}[year]
                        min_spei = {2030: -0.6, 2050: -1.0, 2070: -1.4, 2100: -1.7}[year]
                    else:
                        max_depth = {2030: 0.3, 2050: 0.5, 2070: 0.7, 2100: 0.8}[year]
                        min_spei = {2030: -0.4, 2050: -0.5, 2070: -0.7, 2100: -0.8}[year]

                    depth_noise = (random.random() - 0.5) * 0.3
                    inundation_depth = round(max(0.0, max_depth + depth_noise), 4)
                    flood_level = get_flood_risk_level(inundation_depth)
                    flood_prob = round(0.02 + (inundation_depth / 3.5) * 0.38, 4)

                    spei_noise = random.gauss(0, 0.25)
                    spei_raw = min_spei + spei_noise
                    spei_upper = min(-0.2, spei_raw)
                    spei_lower = max(min_spei - 0.3, spei_upper)
                    spei = round(spei_lower, 4)
                    drought_level_desc = get_drought_level(spei)
                    drought_level_map = {'无旱': '无', '轻旱': '低', '中旱': '中', '重旱': '高', '特旱': '极高'}
                    drought_level = drought_level_map.get(drought_level_desc, '中')
                    drought_months = max(1, min(9, int(abs(spei) * 3 + random.randint(0, 2))))

                    f_score = flood_score_map.get(flood_level, 50)
                    d_score = drought_score_map.get(drought_level, 50)
                    vuln_score = calc_vulnerability_score(f_score, d_score, struct_score)
                    vuln_category = get_vulnerability_level(vuln_score)

                    risk_wkt = _generate_risk_polygon(site.longitude, site.latitude, inundation_depth)
                    try:
                        risk_geom = from_shape(wkt.loads(risk_wkt), srid=4326)
                    except (ImportError, Exception):
                        risk_geom = None

                    records.append({
                        'site_id': site.id,
                        'scenario': scenario,
                        'assessment_year': year,
                        'flood_risk_level': flood_level,
                        'flood_inundation_depth_m': inundation_depth,
                        'flood_exposure_probability': flood_prob,
                        'drought_risk_level': drought_level,
                        'drought_severity_spei': spei,
                        'drought_month_count': drought_months,
                        'overall_vulnerability_score': vuln_score,
                        'vulnerability_category': vuln_category,
                        'risk_zone_geom': risk_geom,
                        'risk_factors': {
                            'temperature_change_c': temp_change,
                            'precipitation_change_pct': round(avg_precip, 2),
                            'region': region,
                            'preservation_status': site.preservation_status,
                        },
                        'adaptation_suggestions': {
                            'category': vuln_category,
                            'scenario': scenario,
                            'target_year': year,
                        },
                    })

        print(f"  → 共生成 {len(records)} 条脆弱性评估")
        batch_size = 500
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            stmt = insert(ClimateVulnerabilityAssessment).values(batch)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['site_id', 'scenario', 'assessment_year']
            )
            result = db.execute(stmt)
            db.commit()
            print(f"    · 批次 {i//batch_size+1}: 处理 {len(batch)} 条")

        _publish_event('CLIMATE_VULNERABILITY_COMPLETED', {
            'total_sites': len(sites),
            'scenarios': scenarios,
            'years': FUTURE_YEARS,
            'total_assessments': len(records),
        })
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ 气候脆弱性评估写入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if need_close:
            db.close()


# ========== 数字化3D重建 ==========
def generate_digital_reconstructions(db=None, generate_vr: bool = True):
    """为遗址生成数字化3D重建数据（按规模概率分布）"""
    random.seed(42)
    try:
        from common.models import DigitalReconstruction, WaterHeritageSite
        from sqlalchemy.dialects.postgresql import insert
        import json
        import datetime
    except ImportError as e:
        print(f"⚠️  缺少依赖，跳过数字化重建: {e}")
        return False

    need_close = False
    if db is None:
        try:
            from common.database import SessionLocal, init_db
            init_db()
            db = SessionLocal()
            need_close = True
        except ImportError as e:
            print(f"⚠️  缺少数据库依赖: {e}")
            return False

    print("🏗️  正在生成数字化3D重建数据...")
    try:
        sites = db.query(WaterHeritageSite).all()
        print(f"  → 查询到 {len(sites)} 处遗址")

        records = []
        vr_count = 0
        steps = ['项目初始化', '影像采集', '特征点匹配', '点云生成', '网格构建',
                 '纹理映射', '模型简化', '质量检查', '最终交付']

        for site in sites:
            irr_area = site.irrigation_area or 0
            if irr_area > 5000:
                prob = 0.60
            elif irr_area > 500:
                prob = 0.35
            else:
                prob = 0.15

            if random.random() > prob:
                continue

            methods = ['摄影测量', '激光扫描', '参数化建模']
            method_weights = [0.70, 0.20, 0.10]
            method = random.choices(methods, weights=method_weights, k=1)[0]

            photos = random.randint(8, 156)
            log_norm_mu = 13.5
            log_norm_sigma = 0.8
            point_cloud = max(100000, min(5000000, int(math.exp(random.gauss(log_norm_mu, log_norm_sigma)))))
            mesh_faces = max(50000, min(2000000, int(point_cloud * (0.05 + random.random() * 0.15))))

            tex_options = ['1K', '2K', '4K']
            tex_weights = [0.20, 0.60, 0.20]
            texture_res = random.choices(tex_options, weights=tex_weights, k=1)[0]

            has_irr_data = site.irrigation_area is not None and site.irrigation_area > 0
            overlay_irr = has_irr_data and (random.random() < 0.90)

            status_options = ['已完成', '失败']
            status_weights = [0.90, 0.10]
            status = random.choices(status_options, weights=status_weights, k=1)[0]

            model_base = f"/models/reconstructions/site_{site.id}"
            glb_url = f"{model_base}/model.glb" if status == '已完成' else None
            gltf_url = f"{model_base}/model.gltf" if status == '已完成' else None
            vr_url = f"{model_base}/vr/index.html" if (status == '已完成' and generate_vr and random.random() < 0.75) else None
            if vr_url:
                vr_count += 1

            base_time = datetime.datetime(2024, 1, 15, 9, 0, 0)
            recon_log = []
            cum_sec = 0
            for idx, step in enumerate(steps):
                step_seconds = random.randint(60, 1800)
                cum_sec += step_seconds
                step_status = '成功' if status == '已完成' else ('失败' if idx == len(steps) - 1 and random.random() < 0.5 else '成功')
                recon_log.append({
                    'step': idx + 1,
                    'step_name': step,
                    'timestamp': (base_time + datetime.timedelta(seconds=cum_sec)).isoformat(),
                    'duration_seconds': step_seconds,
                    'status': step_status,
                })

            records.append({
                'site_id': site.id,
                'photos_uploaded_count': photos,
                'reconstruction_method': method,
                'reconstruction_status': status,
                'point_cloud_count': point_cloud,
                'mesh_face_count': mesh_faces,
                'texture_resolution': texture_res,
                'glb_model_url': glb_url,
                'gltf_model_url': gltf_url,
                'vr_experience_url': vr_url,
                'model_metadata': {
                    'irrigation_area_mu': irr_area,
                    'site_type': site.site_type,
                    'dynasty': site.dynasty,
                },
                'overlay_with_irrigation': overlay_irr,
                'reconstruction_log': recon_log,
            })

        print(f"  → 生成 {len(records)} 条重建记录，其中 VR 体验: {vr_count} 个")
        if records:
            stmt = insert(DigitalReconstruction).values(records)
            stmt = stmt.on_conflict_do_nothing()
            result = db.execute(stmt)
            db.commit()
            inserted = result.rowcount if hasattr(result, 'rowcount') else '批量'
            print(f"  ✅ UPSERT完成，新增: {inserted} 条")

        _publish_event('DIGITAL_RECONSTRUCTION_COMPLETED', {
            'total_sites': len(sites),
            'reconstructed_count': len(records),
            'vr_count': vr_count,
        })
        if generate_vr and vr_count > 0:
            _publish_event('VR_EXPERIENCE_GENERATED', {
                'vr_count': vr_count,
                'sites': [r['site_id'] for r in records if r.get('vr_experience_url')],
            })
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ 数字化重建写入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if need_close:
            db.close()


# ========== 区域水利网络分析 ==========
def generate_network_analysis_regions(db=None):
    """遍历12区域，对遗址数≥3的区域生成水利网络分析"""
    random.seed(42)
    try:
        from common.models import (
            HydraulicNetworkAnalysis, NetworkMemberSite, WaterHeritageSite
        )
        from sqlalchemy.dialects.postgresql import insert
        import json
    except ImportError as e:
        print(f"⚠️  缺少依赖，跳过网络分析: {e}")
        return False

    need_close = False
    if db is None:
        try:
            from common.database import SessionLocal, init_db
            init_db()
            db = SessionLocal()
            need_close = True
        except ImportError as e:
            print(f"⚠️  缺少数据库依赖: {e}")
            return False

    print("🕸️  正在生成区域水利网络分析...")
    try:
        all_sites = db.query(WaterHeritageSite).all()
        region_sites_map = {}
        for site in all_sites:
            region_idx = int(hashlib.md5(site.name.encode()).hexdigest(), 16) % len(REGIONS)
            region = REGIONS[region_idx]
            if region not in region_sites_map:
                region_sites_map[region] = []
            region_sites_map[region].append(site)

        valid_regions = [(r, ss) for r, ss in region_sites_map.items() if len(ss) >= 3]
        print(f"  → 共 {len(REGIONS)} 区域，遗址数≥3的有 {len(valid_regions)} 个")

        total_member_records = 0
        for region, sites in valid_regions:
            n = len(sites)
            max_edges = n * (n - 1) // 2
            connectivity = 0.35 + random.random() * 0.55
            total_edges = max(n - 1, int(max_edges * connectivity))

            network_connectivity = round(connectivity, 4)
            redundancy = round(0.20 + random.random() * 0.55, 4)
            avg_path = round(1.2 + random.random() * 2.8, 4)
            clustering = round(0.25 + random.random() * 0.55, 4)
            synergy = round(0.30 + random.random() * 0.60, 4)
            cascade_eff = round(0.40 + random.random() * 0.50, 4)
            flood_reg = round(0.35 + random.random() * 0.55, 4)

            edge_geojson = {
                "type": "FeatureCollection",
                "features": []
            }
            used_pairs = set()
            edge_count = 0
            sorted_sites = sorted(sites, key=lambda s: s.irrigation_area or 0, reverse=True)
            for i in range(len(sorted_sites)):
                for j in range(i + 1, len(sorted_sites)):
                    if edge_count >= total_edges:
                        break
                    pair = (sorted_sites[i].id, sorted_sites[j].id)
                    if pair in used_pairs:
                        continue
                    if random.random() < (0.9 if i < 3 else 0.3):
                        used_pairs.add(pair)
                        edge_count += 1
                        dist_km = 5 + random.random() * 60
                        edge_geojson['features'].append({
                            "type": "Feature",
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [
                                    [sorted_sites[i].longitude, sorted_sites[i].latitude],
                                    [sorted_sites[j].longitude, sorted_sites[j].latitude],
                                ]
                            },
                            "properties": {
                                "source_site_id": sorted_sites[i].id,
                                "target_site_id": sorted_sites[j].id,
                                "distance_km": round(dist_km, 2),
                                "capacity_class": '干渠级' if dist_km > 30 else '支渠级',
                            }
                        })
                if edge_count >= total_edges:
                    break

            critical_nodes = []
            for idx, s in enumerate(sorted_sites[:max(1, n // 5)]):
                critical_nodes.append({
                    "site_id": s.id,
                    "site_name": s.name,
                    "criticality_score": round(0.70 + random.random() * 0.30, 4),
                    "failure_impact": "流域级" if idx == 0 else ("区域级" if idx < 3 else "本地级"),
                })

            analysis_record = {
                'region': region,
                'total_nodes': n,
                'total_edges': total_edges,
                'network_connectivity': network_connectivity,
                'network_redundancy': redundancy,
                'avg_path_length': avg_path,
                'clustering_coefficient': clustering,
                'synergy_score': synergy,
                'cascade_irrigation_efficiency': cascade_eff,
                'flood_regulation_capacity': flood_reg,
                'critical_nodes': critical_nodes,
                'network_edges_geojson': edge_geojson,
            }

            stmt = insert(HydraulicNetworkAnalysis).values([analysis_record])
            result = db.execute(stmt)
            db.flush()

            inserted_id = None
            if hasattr(result, 'inserted_primary_key'):
                inserted_id = result.inserted_primary_key[0]
            else:
                latest = db.query(HydraulicNetworkAnalysis).filter(
                    HydraulicNetworkAnalysis.region == region
                ).order_by(HydraulicNetworkAnalysis.id.desc()).first()
                inserted_id = latest.id if latest else None

            if inserted_id:
                member_records = []
                sites_sorted = sorted(sites, key=lambda s: s.irrigation_area or 0, reverse=True)
                for rank, s in enumerate(sites_sorted):
                    degree = min(n - 1, max(1, int((total_edges * 2 / max(1, n)) * (0.5 + random.random() * 1.5))))
                    betweenness = round(0.01 + (1.0 - rank / max(1, n)) * (0.1 + random.random() * 0.4), 6)
                    closeness = round(0.20 + (1.0 - rank / max(1, n)) * (0.3 + random.random() * 0.4), 6)
                    if rank == 0:
                        role = '核心枢纽'
                    elif rank < max(2, n // 4):
                        role = '中转节点'
                    elif degree > 1:
                        role = '终端节点'
                    else:
                        role = '孤立节点'
                    member_records.append({
                        'network_analysis_id': inserted_id,
                        'site_id': s.id,
                        'node_degree': degree,
                        'node_betweenness': betweenness,
                        'node_closeness': closeness,
                        'node_role': role,
                    })
                if member_records:
                    stmt_m = insert(NetworkMemberSite).values(member_records)
                    stmt_m = stmt_m.on_conflict_do_nothing()
                    db.execute(stmt_m)
                    total_member_records += len(member_records)

            db.commit()
            print(f"    · {region}: {n}节点/{total_edges}边 完成")

        _publish_event('NETWORK_ANALYSIS_COMPLETED', {
            'total_regions': len(REGIONS),
            'analyzed_regions': len(valid_regions),
            'total_nodes': sum(len(s) for _, s in valid_regions),
            'total_member_records': total_member_records,
        })
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ 网络分析写入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if need_close:
            db.close()


# ========== CLI ==========
def main():
    parser = argparse.ArgumentParser(
        description='古代水利工程遗迹数据模拟器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                                    # 默认300处，全朝代全类型
  %(prog)s --sites 500                        # 500处遗迹
  %(prog)s --dynasty 唐                       # 仅唐代
  %(prog)s --dynasty 宋                       # 宋代（北宋+南宋）
  %(prog)s --type 渠,堰                       # 仅渠和堰
  %(prog)s --sites 100 --dynasty 明 --type 塘 # 明代100处塘
  %(prog)s --no-hydrology                     # 不生成水文数据
  %(prog)s --hydro-only                       # 仅生成水文数据
  %(prog)s --list-dynasties                   # 列出所有朝代
  %(prog)s --gen-crop-yields                  # 生成古代作物产量基准(1020条)
  %(prog)s --gen-agriculture-impact           # 生成农业影响评估
  %(prog)s --gen-climate-scenarios            # 生成气候脆弱性评估
  %(prog)s --gen-digital-models               # 生成数字化3D重建
  %(prog)s --gen-network                      # 生成区域水利网络分析
  %(prog)s --gen-all-new                      # 一次生成所有新功能数据
        """
    )
    parser.add_argument('--sites', type=int, default=300,
                        help='生成遗迹数量 (默认: 300)')
    parser.add_argument('--dynasty', type=str, default='all',
                        help='朝代过滤，如：唐、宋、明 (默认: all)')
    parser.add_argument('--type', type=str, default='all',
                        help='工程类型，逗号分隔，如：渠,堰,陂 (默认: all)')
    parser.add_argument('--seed', type=int, default=42,
                        help='随机种子 (默认: 42)')
    parser.add_argument('--no-hydrology', action='store_true',
                        help='不生成水文数据')
    parser.add_argument('--hydro-only', action='store_true',
                        help='仅生成水文数据，不生成遗迹')
    parser.add_argument('--list-dynasties', action='store_true',
                        help='列出所有支持的朝代并退出')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅生成数据，不写入数据库')
    parser.add_argument('--gen-crop-yields', action='store_true',
                        help='生成古代作物产量基准数据')
    parser.add_argument('--gen-agriculture-impact', action='store_true',
                        help='为已有遗址生成农业影响评估')
    parser.add_argument('--gen-climate-scenarios', action='store_true',
                        help='生成气候脆弱性评估')
    parser.add_argument('--gen-digital-models', action='store_true',
                        help='生成数字化3D重建数据')
    parser.add_argument('--gen-network', action='store_true',
                        help='生成区域水利网络分析')
    parser.add_argument('--gen-all-new', action='store_true',
                        help='一次生成所有新功能数据')

    args = parser.parse_args()

    # 列出朝代
    if args.list_dynasties:
        print("📜 支持的朝代列表:")
        print("-" * 50)
        for d in DYNASTIES:
            years = f"{d['start_year']}~{d['end_year']}"
            years = years.replace('--', '前').replace('-', '前')
            if '前' in years and '~' in years:
                parts = years.split('~')
                if not parts[1].startswith('前') and not parts[0].startswith('前'):
                    pass
            print(f"  {d['order']:2d}. {d['name']:<4s} ({years:>12s})  权重: {d['weight']:.0%}")
        print()
        print("可用类型: 渠, 堰, 陂, 塘, 井")
        return

    # 参数校验
    if args.sites <= 0:
        print("❌ --sites 必须大于 0")
        sys.exit(1)

    print("=" * 60)
    print("🏛️  古代水利工程遗迹数据模拟器")
    print("=" * 60)
    print(f"📝 配置:")
    is_new_feature_mode = any([
        args.gen_crop_yields, args.gen_agriculture_impact,
        args.gen_climate_scenarios, args.gen_digital_models,
        args.gen_network, args.gen_all_new
    ])
    if not is_new_feature_mode and not args.hydro_only:
        print(f"  遗迹数量:   {args.sites}")
        print(f"  朝代过滤:   {args.dynasty}")
        print(f"  类型过滤:   {args.type}")
    if not is_new_feature_mode:
        print(f"  随机种子:   {args.seed}")
        print(f"  生成水文:   {'否' if args.no_hydrology else '是'}")
    print(f"  写入数据库: {'否' if args.dry_run else '是'}")
    if is_new_feature_mode:
        print(f"  新功能:")
        if args.gen_all_new:
            print(f"    全部生成: 是")
        else:
            print(f"    作物产量:   {'是' if args.gen_crop_yields else '否'}")
            print(f"    农业影响:   {'是' if args.gen_agriculture_impact else '否'}")
            print(f"    气候评估:   {'是' if args.gen_climate_scenarios else '否'}")
            print(f"    3D重建:     {'是' if args.gen_digital_models else '否'}")
            print(f"    网络分析:   {'是' if args.gen_network else '否'}")
    print()

    sites = []
    hydrology = []
    used_dynasties = DYNASTIES

    if not is_new_feature_mode:
        # 生成遗迹
        if not args.hydro_only:
            print(f"🏗️  正在生成 {args.sites} 处遗迹...")
            sites, used_dynasties = generate_sites(
                args.sites,
                dynasty_filter=args.dynasty,
                type_filter=args.type,
                seed=args.seed
            )

            type_counts = {}
            dynasty_counts = {}
            status_counts = {}
            for s in sites:
                type_counts[s['site_type']] = type_counts.get(s['site_type'], 0) + 1
                dynasty_counts[s['dynasty']] = dynasty_counts.get(s['dynasty'], 0) + 1
                status_counts[s['preservation_status']] = status_counts.get(s['preservation_status'], 0) + 1

            print(f"  类型分布: {type_counts}")
            print(f"  朝代分布: {dynasty_counts}")
            print(f"  保存状态: {status_counts}")
            print()

        # 生成水文
        if not args.no_hydrology:
            print(f"🌧️  正在生成水文重建数据...")
            hydrology = generate_hydrology(dynasties=used_dynasties, seed=args.seed + 1)
            print(f"  共 {len(hydrology)} 条记录")
            print(f"  覆盖区域: {len(REGIONS)} 个")
            print(f"  时间范围: 每10年分辨率")
            print()

        # 写入数据库
        if args.dry_run:
            print("⏭️  Dry-Run 模式，跳过数据库写入")
            print(f"   遗迹: {len(sites)} 处")
            print(f"   水文: {len(hydrology)} 条")
        else:
            ok = insert_to_database(sites, hydrology, used_dynasties)
            if not ok:
                print("\n💡 提示: 使用 --dry-run 仅生成数据不写入数据库")
                sys.exit(1)
    else:
        if args.dry_run:
            print("⏭️  Dry-Run 模式下新功能无法生成（需数据库连接）")
            sys.exit(0)

    # ========== 新功能数据生成 ==========
    if is_new_feature_mode:
        db_session = None
        try:
            from common.database import SessionLocal, init_db
            init_db()
            db_session = SessionLocal()
            print("🔌 已建立数据库连接用于新功能数据生成")
            print()
        except ImportError as e:
            print(f"❌ 无法建立数据库连接: {e}")
            sys.exit(1)

        try:
            results = {}

            if args.gen_all_new or args.gen_crop_yields:
                results['crop_yields'] = insert_ancient_crop_yields(db_session)
                print()

            if args.gen_all_new or args.gen_agriculture_impact:
                results['agriculture_impact'] = generate_agriculture_impact_batch(db_session)
                print()

            if args.gen_all_new or args.gen_climate_scenarios:
                results['climate_vulnerability'] = generate_climate_vulnerability_batch(db_session)
                print()

            if args.gen_all_new or args.gen_digital_models:
                results['digital_reconstructions'] = generate_digital_reconstructions(db_session)
                print()

            if args.gen_all_new or args.gen_network:
                results['network_analysis'] = generate_network_analysis_regions(db_session)
                print()

            print("📊 新功能执行结果:")
            for k, v in results.items():
                status_icon = "✅" if v else "❌"
                print(f"  {status_icon} {k}: {'成功' if v else '失败'}")

        finally:
            if db_session:
                db_session.close()
                print("🔌 数据库连接已关闭")

    print()
    print("🎉 模拟完成！")


if __name__ == '__main__':
    main()
