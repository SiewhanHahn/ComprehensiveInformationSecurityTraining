import echarts from './echarts'

let mapPromise = null

// 懒加载中国地图 GeoJSON 并注册；失败时记住失败结果，避免反复请求
export function ensureChinaMap() {
  if (!mapPromise) {
    mapPromise = import('../assets/china.json')
      .then((mod) => {
        echarts.registerMap('china', mod.default || mod)
      })
      .catch((err) => {
        mapPromise = null
        throw err
      })
  }
  return mapPromise
}
