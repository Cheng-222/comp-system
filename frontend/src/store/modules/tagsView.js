const useTagsViewStore = defineStore(
  'tags-view',
  {
    state: () => ({
      visitedViews: [],
      cachedViews: [],
      iframeViews: []
    }),
    actions: {
      normalizeView(view) {
        if (!view) return view
        if (view.path === '/competition/dashboard') {
          return {
            ...view,
            fullPath: '/index',
            path: '/index',
            name: 'Index',
            meta: {
              ...(view.meta || {}),
              title: '首页',
              affix: true
            },
            title: '首页'
          }
        }
        return view
      },
      repairViews() {
        this.visitedViews = this.visitedViews.reduce((result, item) => {
          const normalizedItem = this.normalizeView(item)
          if (!normalizedItem?.path) return result
          if (result.some(view => view.path === normalizedItem.path)) return result
          result.push(normalizedItem)
          return result
        }, [])
        this.iframeViews = this.iframeViews.reduce((result, item) => {
          const normalizedItem = this.normalizeView(item)
          if (!normalizedItem?.path) return result
          if (result.some(view => view.path === normalizedItem.path)) return result
          result.push(normalizedItem)
          return result
        }, [])
        this.cachedViews = this.cachedViews.filter(Boolean)
      },
      addView(view) {
        const normalizedView = this.normalizeView(view)
        this.addVisitedView(normalizedView)
        this.addCachedView(normalizedView)
      },
      addIframeView(view) {
        const normalizedView = this.normalizeView(view)
        if (this.iframeViews.some(v => v.path === normalizedView.path)) return
        this.iframeViews.push(
          Object.assign({}, normalizedView, {
            title: normalizedView.meta.title || 'no-name'
          })
        )
      },
      addVisitedView(view) {
        const normalizedView = this.normalizeView(view)
        if (this.visitedViews.some(v => v.path === normalizedView.path)) return
        this.visitedViews.push(
          Object.assign({}, normalizedView, {
            title: normalizedView.meta.title || 'no-name'
          })
        )
      },
      addCachedView(view) {
        const normalizedView = this.normalizeView(view)
        if (this.cachedViews.includes(normalizedView.name)) return
        if (!normalizedView.meta?.noCache && normalizedView.name) {
          this.cachedViews.push(normalizedView.name)
        }
      },
      delView(view) {
        return new Promise(resolve => {
          this.delVisitedView(view)
          this.delCachedView(view)
          resolve({
            visitedViews: [...this.visitedViews],
            cachedViews: [...this.cachedViews]
          })
        })
      },
      delVisitedView(view) {
        return new Promise(resolve => {
          for (const [i, v] of this.visitedViews.entries()) {
            if (v.path === view.path) {
              this.visitedViews.splice(i, 1)
              break
            }
          }
          this.iframeViews = this.iframeViews.filter(item => item.path !== view.path)
          resolve([...this.visitedViews])
        })
      },
      delIframeView(view) {
        return new Promise(resolve => {
          this.iframeViews = this.iframeViews.filter(item => item.path !== view.path)
          resolve([...this.iframeViews])
        })
      },
      delCachedView(view) {
        return new Promise(resolve => {
          const index = this.cachedViews.indexOf(view.name)
          index > -1 && this.cachedViews.splice(index, 1)
          resolve([...this.cachedViews])
        })
      },
      delOthersViews(view) {
        return new Promise(resolve => {
          this.delOthersVisitedViews(view)
          this.delOthersCachedViews(view)
          resolve({
            visitedViews: [...this.visitedViews],
            cachedViews: [...this.cachedViews]
          })
        })
      },
      delOthersVisitedViews(view) {
        return new Promise(resolve => {
          this.visitedViews = this.visitedViews.filter(v => {
            return v.meta.affix || v.path === view.path
          })
          this.iframeViews = this.iframeViews.filter(item => item.path === view.path)
          resolve([...this.visitedViews])
        })
      },
      delOthersCachedViews(view) {
        return new Promise(resolve => {
          const index = this.cachedViews.indexOf(view.name)
          if (index > -1) {
            this.cachedViews = this.cachedViews.slice(index, index + 1)
          } else {
            this.cachedViews = []
          }
          resolve([...this.cachedViews])
        })
      },
      delAllViews(view) {
        return new Promise(resolve => {
          this.delAllVisitedViews(view)
          this.delAllCachedViews(view)
          resolve({
            visitedViews: [...this.visitedViews],
            cachedViews: [...this.cachedViews]
          })
        })
      },
      delAllVisitedViews(view) {
        return new Promise(resolve => {
          const affixTags = this.visitedViews.filter(tag => tag.meta.affix)
          this.visitedViews = affixTags
          this.iframeViews = []
          resolve([...this.visitedViews])
        })
      },
      delAllCachedViews(view) {
        return new Promise(resolve => {
          this.cachedViews = []
          resolve([...this.cachedViews])
        })
      },
      updateVisitedView(view) {
        view = this.normalizeView(view)
        for (let v of this.visitedViews) {
          if (v.path === view.path) {
            v = Object.assign(v, view)
            break
          }
        }
      },
      delRightTags(view) {
        return new Promise(resolve => {
          const index = this.visitedViews.findIndex(v => v.path === view.path)
          if (index === -1) {
            return
          }
          this.visitedViews = this.visitedViews.filter((item, idx) => {
            if (idx <= index || (item.meta && item.meta.affix)) {
              return true
            }
            const i = this.cachedViews.indexOf(item.name)
            if (i > -1) {
              this.cachedViews.splice(i, 1)
            }
            if(item.meta.link) {
              const fi = this.iframeViews.findIndex(v => v.path === item.path)
              this.iframeViews.splice(fi, 1)
            }
            return false
          })
          resolve([...this.visitedViews])
        })
      },
      delLeftTags(view) {
        return new Promise(resolve => {
          const index = this.visitedViews.findIndex(v => v.path === view.path)
          if (index === -1) {
            return
          }
          this.visitedViews = this.visitedViews.filter((item, idx) => {
            if (idx >= index || (item.meta && item.meta.affix)) {
              return true
            }
            const i = this.cachedViews.indexOf(item.name)
            if (i > -1) {
              this.cachedViews.splice(i, 1)
            }
            if(item.meta.link) {
              const fi = this.iframeViews.findIndex(v => v.path === item.path)
              this.iframeViews.splice(fi, 1)
            }
            return false
          })
          resolve([...this.visitedViews])
        })
      }
    }
  })

export default useTagsViewStore
