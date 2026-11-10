/**
 * tripscout — pannello Hermes Desktop.
 *
 * Quattro domande e basta: da dove parti, dove vuoi andare, in che finestra di
 * date, con che vincoli. Nessun filtro nascosto: i giorni di partenza non si
 * filtrano (si parte quando si vuole), le destinazioni si cercano scrivendo.
 */

import { cn, host, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useCallback, useEffect, useMemo, useState } from 'react'

const ID = 'tripscout'

// Quando "anywhere" è acceso il pannello sceglie lui le destinazioni: così non
// dipende dal fatto che il backend conosca la parola magica "any".
const CHEAP_FIRST = [
  'Budapest', 'Praga', 'Cracovia', 'Varsavia', 'Bratislava', 'Lubiana',
  'Sofia', 'Riga', 'Vilnius', 'Tallinn', 'Zagabria', 'Belgrado',
  'Bucarest', 'Cluj', 'Danzica', 'Brno', 'Porto', 'Valencia'
]

let API = null

const HAIRLINE = { borderColor: 'var(--ui-stroke-secondary)' }

const chipBase =
  'inline-flex items-center rounded-full border px-2 py-[1px] text-[0.6875rem] leading-5 transition-colors'
const chipOff = 'border-(--ui-stroke-secondary) text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)'
const chipOn = 'border-(--ui-accent) text-(--ui-accent) bg-(--chrome-action-hover)'
const tag = 'rounded-sm border border-(--ui-stroke-secondary) px-1 text-[0.625rem] uppercase tracking-wide text-(--ui-text-quaternary)'
const labelText = 'text-[0.6875rem] font-medium uppercase tracking-wider text-(--ui-text-quaternary)'
const muted = 'text-[0.6875rem] text-(--ui-text-quaternary)'
const field =
  'w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs text-foreground outline-none focus:border-(--ui-accent)'

function isoIn(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

function shortDate(iso) {
  if (!iso) return ''
  const [, m, d] = iso.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${Number(d)} ${months[Number(m) - 1] || m}`
}

function Chip({ on, children, onClick, title }) {
  return jsx('button', {
    type: 'button',
    title,
    className: cn(chipBase, on ? chipOn : chipOff),
    onClick,
    children
  })
}

function Section({ title, aside, children }) {
  return jsxs('section', {
    className: 'flex flex-col gap-1.5 border-t pt-2.5',
    style: HAIRLINE,
    children: [
      jsxs('div', {
        className: 'flex items-baseline justify-between',
        children: [
          jsx('div', { className: labelText, children: title }),
          aside ? jsx('div', { className: muted, children: aside }) : null
        ]
      }),
      children
    ]
  })
}

function Breakdown({ option }) {
  const est = option.estimate
  const line = (text, className) => jsx('div', { className: className || 'text-(--ui-text-secondary)', children: text })
  return jsxs('div', {
    className: 'mt-2 flex flex-col gap-1 border-l pl-2 text-[0.6875rem]',
    style: HAIRLINE,
    children: [
      line(`${option.currency || 'EUR'} ${option.flight.toFixed(0)} flight · ${option.hotel.toFixed(0)} stay (${option.hotel_name})`),
      line(`${option.access.toFixed(0)} getting to ${option.from} · ${option.airport_transfer.toFixed(0)} airport↔town`),
      est
        ? line(
            `+ ${est.food_total.toFixed(0)} food + ${est.activities_total.toFixed(0)} tickets → ${option.total_with_estimates.toFixed(0)} all-in (estimate)`,
            'text-(--ui-text-quaternary)'
          )
        : null,
      option.flight_departure ? line(`${(option.airlines || []).join(', ') || 'flight'} · ${option.flight_departure}`, 'text-(--ui-text-quaternary)') : null
    ]
  })
}

function TripscoutPane() {
  const gateway = useValue(host.state.gateway)
  const [presets, setPresets] = useState(null)
  const [home, setHome] = useState('Prato')
  const [picked, setPicked] = useState([])
  const [mode, setMode] = useState('anywhere') // cheapest | anywhere | picked
  const [destFilter, setDestFilter] = useState('')
  const [nightsMin, setNightsMin] = useState(2)
  const [nightsMax, setNightsMax] = useState(4)
  const [dateFrom, setDateFrom] = useState(() => isoIn(12))
  const [dateTo, setDateTo] = useState(() => isoIn(40))
  const [lodging, setLodging] = useState(['any'])
  const [adults, setAdults] = useState(1)
  const [budget, setBudget] = useState('')
  const [estimates, setEstimates] = useState(true)
  const [jobId, setJobId] = useState(null)
  const [job, setJob] = useState(null)
  const [open, setOpen] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!API || typeof API.rest !== 'function') {
      setError('this build of Hermes Desktop does not expose ctx.rest — use the tripscout tools from chat instead')
      return
    }
    let alive = true
    try {
      API.rest('/presets')
        .then(data => alive && setPresets(data))
        .catch(err => alive && setError(String(err && err.message ? err.message : err)))
    } catch (err) {
      setError(String(err && err.message ? err.message : err))
    }
    return () => {
      alive = false
    }
  }, [gateway])

  useEffect(() => {
    if (!jobId || !API) return
    let alive = true
    const tick = async () => {
      try {
        const next = await API.rest(`/jobs/${jobId}`)
        if (!alive) return
        setJob(next)
        if (next.status !== 'running') setJobId(null)
      } catch (err) {
        if (!alive) return
        setError(String(err && err.message ? err.message : err))
        setJobId(null)
      }
    }
    tick()
    const timer = setInterval(tick, 1200)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [jobId])

  const allCities = useMemo(() => (presets ? presets.destinations : []), [presets])
  const homes = useMemo(() => (presets ? presets.home_cities : []), [presets])
  const shown = useMemo(() => {
    const needle = destFilter.trim().toLowerCase()
    if (!needle) return allCities
    return allCities.filter(
      city =>
        city.city.toLowerCase().includes(needle) ||
        (city.country || '').toLowerCase().includes(needle) ||
        (city.airports || []).join(' ').toLowerCase().includes(needle)
    )
  }, [allCities, destFilter])

  const togglePicked = useCallback(name => {
    setMode('picked')
    setPicked(current =>
      current.includes(name) ? current.filter(c => c !== name) : [...current, name].slice(0, 12)
    )
  }, [])

  // shortlist: le prime 8 città "economiche prima" presenti nel catalogo
  const shortlist = useCallback(() => {
    const byName = new Map(allCities.map(city => [city.city, city.city]))
    const out = CHEAP_FIRST.filter(name => byName.has(name)).slice(0, 8)
    if (out.length >= 8) return out
    for (const city of allCities) {
      if (out.length >= 8) break
      if (!out.includes(city.city)) out.push(city.city)
    }
    return out
  }, [allCities])

  const toggleLodging = useCallback(kind => {
    setLodging(current => {
      if (kind === 'any') return ['any']
      const without = current.filter(k => k !== 'any')
      const next = without.includes(kind) ? without.filter(k => k !== kind) : [...without, kind]
      return next.length ? next : ['any']
    })
  }, [])

  const run = useCallback(async () => {
    if (!API) return
    if (!home.trim()) {
      setError('write where you are leaving from')
      return
    }
    if (mode === 'picked' && !picked.length) {
      setError('pick a destination, or switch "anywhere" or "cheapest" on')
      return
    }
    const destinationList =
      mode === 'cheapest' ? allCities.map(city => city.city) : mode === 'anywhere' ? shortlist() : picked
    if (!destinationList.length) {
      setError('the city list did not load — reopen the pane')
      return
    }
    setError('')
    setOpen(null)
    const params = {
      home: home.trim(),
      destinations: destinationList,
      max_destinations: 8,
      window_start: dateFrom,
      window_end: dateTo,
      nights_min: nightsMin,
      nights_max: nightsMax,
      weekdays: [
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
      ], // elencati tutti: nessun filtro, e vale anche se gira un backend vecchio
      lodging,
      estimates,
      adults,
      max_requests: 70,
      min_interval: 0.8
    }
    if (budget.trim()) params.budget_total = Number(budget)
    if (mode === 'cheapest') {
      // poche date campionate su tutta la finestra × tutte le città: così il
      // confronto è fra destinazioni, non fra il primo giorno disponibile
      params.max_options = 2
      params.max_requests = 150
      params.min_interval = 0.6
    }
    try {
      setJob({ status: 'running', elapsed_seconds: 0 })
      const started = await API.rest('/search', { method: 'POST', body: params })
      setJobId(started.job_id)
    } catch (err) {
      setError(String(err && err.message ? err.message : err))
      setJob(null)
    }
  }, [home, picked, mode, shortlist, allCities, dateFrom, dateTo, nightsMin, nightsMax, lodging, estimates, adults, budget])

  const running = jobId !== null
  const result = job && job.result ? job.result : null
  const options = result && result.options ? result.options : []
  const stats = result && result.stats ? result.stats : null
  const tried = result && result.query && result.query.destinations ? result.query.destinations : []

  if (!presets) {
    return jsx('div', {
      className: 'flex h-full flex-col items-center justify-center gap-2 p-4 text-xs text-(--ui-text-secondary)',
      children: error || 'tripscout: loading…'
    })
  }

  return jsxs('div', {
    className: 'flex h-full flex-col overflow-auto text-xs',
    children: [
      // ---------- testata ----------
      jsxs('div', {
        className: 'flex items-start justify-between gap-2 pb-2',
        children: [
          jsxs('div', {
            className: 'flex flex-col',
            children: [
              jsx('div', { className: 'text-sm font-semibold tracking-tight', children: 'tripscout' }),
              jsx('div', { className: muted, children: 'flight + bed + getting there, one number' })
            ]
          }),
          jsx('div', {
            className: cn(tag, 'mt-0.5'),
            children: presets.cache ? `${presets.cache.cached_entries} cached` : 'no cache'
          })
        ]
      }),

      // ---------- da dove ----------
      jsx(Section, {
        title: 'leaving from',
        aside: 'town, not airport',
        children: jsxs('div', {
          className: 'flex flex-col gap-1',
          children: [
            jsxs('div', {
              children: [
                jsx('input', {
                  className: field,
                  value: home,
                  list: 'tripscout-homes',
                  placeholder: 'Prato',
                  onChange: event => setHome(event.target.value)
                }),
                jsx('datalist', {
                  id: 'tripscout-homes',
                  children: homes.map(city => jsx('option', { value: city.city }, city.city))
                })
              ]
            }),
            jsx('div', {
              className: muted,
              children: 'every airport serving it, with the train or bus to reach it'
            })
          ]
        })
      }),

      // ---------- dove ----------
      jsx(Section, {
        title: 'where to',
        aside:
          mode === 'cheapest'
            ? `all ${allCities.length} cities`
            : mode === 'anywhere'
              ? `${shortlist().length} cheap-first cities`
              : picked.length ? `${picked.length} picked` : 'nothing picked',
        children: jsxs('div', {
          className: 'flex flex-col gap-1.5',
          children: [
            jsxs('div', {
              className: 'flex items-center gap-1.5',
              children: [
                jsx(Chip, {
                  on: mode === 'cheapest',
                  title: 'compare every known city and keep the cheapest whole trip',
                  onClick: () => {
                    setMode('cheapest')
                    setPicked([])
                  },
                  children: 'cheapest'
                }),
                jsx(Chip, {
                  on: mode === 'anywhere',
                  title: 'a shorter shortlist of cheap-first cities, faster than cheapest',
                  onClick: () => {
                    setMode('anywhere')
                    setPicked([])
                  },
                  children: 'anywhere'
                }),
                jsx('input', {
                  className: cn(field, 'flex-1'),
                  value: destFilter,
                  placeholder: 'filter 49 cities…',
                  onChange: event => setDestFilter(event.target.value)
                })
              ]
            }),
            jsxs('div', {
              className: 'flex max-h-36 flex-wrap gap-1 overflow-auto',
              children: [
                ...shown.slice(0, 60).map(city =>
                  jsx(
                    Chip,
                    {
                      on: mode === 'picked' && picked.includes(city.city),
                      title: `${city.country} · ${city.airports.join(' / ')} · town transfer ${city.transfer_cost}`,
                      onClick: () => togglePicked(city.city),
                      children: city.city
                    },
                    city.city
                  )
                ),
                shown.length === 0
                  ? jsx('div', { className: muted, children: 'no city matches — the engine needs an airport, so pick from the list' })
                  : null
              ]
            })
          ]
        })
      }),

      // ---------- quando ----------
      jsx(Section, {
        title: 'when',
        aside: `${shortDate(dateFrom)} → ${shortDate(dateTo)} · ${nightsMin}–${nightsMax} nights`,
        children: jsxs('div', {
          className: 'flex flex-col gap-2',
          children: [
            jsxs('div', {
              className: 'grid grid-cols-2 gap-2',
              children: [
                jsx('input', {
                  type: 'date',
                  className: field,
                  value: dateFrom,
                  onChange: event => setDateFrom(event.target.value)
                }),
                jsx('input', {
                  type: 'date',
                  className: field,
                  value: dateTo,
                  onChange: event => setDateTo(event.target.value)
                })
              ]
            }),
            jsxs('div', {
              className: 'flex flex-col gap-1',
              children: [
                jsx('div', {
                  className: 'flex items-center justify-between',
                  children: jsx('div', {
                    className: muted,
                    children: 'nights: drag the two handles'
                  })
                }),
                jsx('input', {
                  type: 'range',
                  min: 1,
                  max: 7,
                  value: nightsMin,
                  className: 'w-full accent-(--ui-accent)',
                  onChange: event => {
                    const n = Number(event.target.value)
                    setNightsMin(n)
                    setNightsMax(current => (current < n ? n : current))
                  }
                }),
                jsx('input', {
                  type: 'range',
                  min: 1,
                  max: 7,
                  value: nightsMax,
                  className: 'w-full accent-(--ui-accent)',
                  onChange: event => {
                    const n = Number(event.target.value)
                    setNightsMax(n)
                    setNightsMin(current => (current > n ? n : current))
                  }
                })
              ]
            })
          ]
        })
      }),

      // ---------- vincoli ----------
      jsx(Section, {
        title: 'limits',
        aside: 'none of them required',
        children: jsxs('div', {
          className: 'flex flex-col gap-2',
          children: [
            jsx('div', {
              className: 'flex flex-wrap gap-1',
              children: ['any', 'hostel', 'hotel', 'apartment'].map(kind =>
                jsx(Chip, { on: lodging.includes(kind), onClick: () => toggleLodging(kind), children: kind }, kind)
              )
            }),
            jsxs('div', {
              className: 'grid grid-cols-2 gap-2',
              children: [
                jsxs('label', {
                  className: 'flex flex-col gap-0.5',
                  children: [
                    jsx('span', { className: muted, children: 'travellers' }),
                    jsx('input', {
                      type: 'number',
                      min: 1,
                      max: 9,
                      className: field,
                      value: adults,
                      onChange: event => setAdults(Math.max(1, Number(event.target.value) || 1))
                    })
                  ]
                }),
                jsxs('label', {
                  className: 'flex flex-col gap-0.5',
                  children: [
                    jsx('span', { className: muted, children: 'budget, all in' }),
                    jsx('input', {
                      className: field,
                      value: budget,
                      placeholder: 'no limit',
                      inputMode: 'numeric',
                      onChange: event => setBudget(event.target.value)
                    })
                  ]
                })
              ]
            }),
            jsxs('label', {
              className: 'flex items-center gap-1.5 text-[0.6875rem] text-(--ui-text-secondary)',
              children: [
                jsx('input', {
                  type: 'checkbox',
                  className: 'accent-(--ui-accent)',
                  checked: estimates,
                  onChange: event => setEstimates(event.target.checked)
                }),
                'add food and ticket estimate'
              ]
            })
          ]
        })
      }),

      // ---------- azione ----------
      jsx('div', {
        className: 'py-2',
        children: jsx('button', {
          type: 'button',
          disabled: running,
          onClick: run,
          className: cn(
            'w-full rounded border px-3 py-1.5 text-xs font-medium transition-colors',
            running
              ? 'border-(--ui-stroke-secondary) text-(--ui-text-quaternary)'
              : 'border-(--ui-accent) text-(--ui-accent) hover:bg-(--chrome-action-hover)'
          ),
          children: running ? `searching… ${job ? job.elapsed_seconds.toFixed(0) : 0}s` : 'find the trip'
        })
      }),

      error
        ? jsx('div', {
            className: 'mb-2 rounded border p-2 text-[0.6875rem] text-(--ui-text-secondary)',
            style: HAIRLINE,
            children: error
          })
        : null,

      job && job.error
        ? jsx('div', {
            className: 'mb-2 rounded border p-2 text-[0.6875rem]',
            style: HAIRLINE,
            children: job.error
          })
        : null,

      stats
        ? jsx('div', {
            className: muted,
            children: `${stats.combinations_ranked} trips priced · ${stats.requests_spent} requests · ${stats.cache_hits} from cache · ${stats.elapsed_seconds}s`
          })
        : null,

      tried.length
        ? jsx('div', { className: muted, children: `tried: ${tried.join(' · ')}` })
        : null,

      // ---------- risultati ----------
      jsxs('div', {
        className: 'mt-1.5 flex flex-col gap-1',
        children: [
          options.map((option, index) =>
            jsxs(
              'div',
              {
                className: cn(
                  'cursor-pointer rounded border px-2 py-1.5 transition-colors hover:bg-(--chrome-action-hover)',
                  index === 0 ? 'border-(--ui-accent)' : ''
                ),
                style: index === 0 ? undefined : HAIRLINE,
                onClick: () => setOpen(open === index ? null : index),
                children: [
                  jsxs('div', {
                    className: 'flex items-baseline justify-between gap-2',
                    children: [
                      jsxs('div', {
                        className: 'flex min-w-0 flex-col',
                        children: [
                          jsxs('div', {
                            className: 'flex items-baseline gap-1.5',
                            children: [
                              jsx('span', { className: 'truncate text-xs font-medium', children: option.city }),
                              jsx('span', { className: tag, children: option.lodging_kind })
                            ]
                          }),
                          jsx('div', {
                            className: muted,
                            children: `${option.dates.replace(' → ', ' – ')} · from ${option.from}`
                          })
                        ]
                      }),
                      jsxs('div', {
                        className: 'flex flex-col items-end',
                        children: [
                          jsx('div', { className: 'text-xs font-semibold tabular-nums', children: option.total_text }),
                          option.total_with_estimates
                            ? jsx('div', { className: muted, children: `${option.total_with_estimates.toFixed(0)} all-in` })
                            : null
                        ]
                      })
                    ]
                  }),
                  open === index ? jsx(Breakdown, { option }) : null
                ]
              },
              `${option.city}-${option.dates}-${index}`
            )
          ),
          result && !options.length
            ? jsxs('div', {
                className: 'flex flex-col items-center gap-1 rounded border p-3 text-center',
                style: HAIRLINE,
                children: [
                  jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: 'nothing inside those limits' }),
                  jsx('div', { className: muted, children: 'widen the dates, raise the budget, or switch "anywhere" on' })
                ]
              })
            : null
        ]
      })
    ]
  })
}

export default {
  id: ID,
  name: 'tripscout',
  register(ctx) {
    API = ctx

    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'tripscout',
      data: { placement: 'right', width: '380px' },
      render: () => jsx(TripscoutPane, {})
    })
  }
}
