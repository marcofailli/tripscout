/**
 * tripscout — pannello Hermes Desktop.
 *
 * Tre cose che l'utente decide: da dove parte (testo libero, lo interpreta il
 * backend), dove vuole andare (o "no matter"), e in che finestra di date.
 * Il resto — volo, alloggio, adduzione, transfer — lo fa il motore.
 */

import { cn, host, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useCallback, useEffect, useMemo, useState } from 'react'

const ID = 'tripscout'

let API = null

const WEEKDAYS = [
  { key: 'thursday', label: 'Thu', dow: 4 },
  { key: 'friday', label: 'Fri', dow: 5 },
  { key: 'saturday', label: 'Sat', dow: 6 }
]

const chipBase =
  'inline-flex items-center rounded-full border px-2 py-0.5 text-[0.6875rem] transition-colors'
const chipOff =
  'border-(--ui-stroke-secondary) text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)'
const chipOn = 'border-(--ui-accent) text-(--ui-accent) bg-(--chrome-action-hover)'
const label = 'text-[0.6875rem] uppercase tracking-wide text-(--ui-text-quaternary)'
const field =
  'w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-1.5 py-1 text-xs text-foreground'
const hint = 'text-[0.6875rem] text-(--ui-text-quaternary)'

function isoIn(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
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

function Row({ caption, children }) {
  return jsxs('div', {
    className: 'flex flex-col gap-1',
    children: [jsx('div', { className: label, children: caption }), children]
  })
}

function Breakdown({ option }) {
  const est = option.estimate
  return jsxs('div', {
    className:
      'mt-1 flex flex-col gap-0.5 border-l pl-2 text-[0.6875rem] text-(--ui-text-secondary)',
    style: { borderColor: 'var(--ui-stroke-secondary)' },
    children: [
      jsx('div', {
        children: `${option.flight.toFixed(0)} flight + ${option.hotel.toFixed(0)} stay (${option.hotel_name}, ${option.lodging_kind}) + ${option.access.toFixed(0)} access + ${option.airport_transfer.toFixed(0)} transfer`
      }),
      est
        ? jsx('div', {
            children: `+ ${est.food_total.toFixed(0)} food + ${est.activities_total.toFixed(0)} tickets = ${option.total_with_estimates.toFixed(0)} ${option.currency || ''} all-in (estimate)`
          })
        : null,
      jsx('div', {
        className: hint,
        children: `${(option.airlines || []).join(', ') || 'flight'} · ${option.flight_departure || ''}`
      })
    ]
  })
}

function TripscoutPane() {
  const gateway = useValue(host.state.gateway)
  const [presets, setPresets] = useState(null)
  const [home, setHome] = useState('Prato')
  const [picked, setPicked] = useState([])
  const [anywhere, setAnywhere] = useState(true)
  const [nightsMin, setNightsMin] = useState(2)
  const [nightsMax, setNightsMax] = useState(4)
  const [dateFrom, setDateFrom] = useState(() => isoIn(12))
  const [dateTo, setDateTo] = useState(() => isoIn(40))
  const [days, setDays] = useState(['thursday', 'friday'])
  const [lodging, setLodging] = useState(['any'])
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
    const timer = setInterval(tick, 1500)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [jobId])

  const allCities = useMemo(() => (presets ? presets.destinations : []), [presets])
  const knownHomes = useMemo(() => (presets ? presets.home_cities : []), [presets])

  const togglePicked = useCallback(name => {
    setAnywhere(false)
    setPicked(current =>
      current.includes(name) ? current.filter(c => c !== name) : [...current, name].slice(0, 12)
    )
  }, [])

  const toggleAnywhere = useCallback(() => {
    setAnywhere(current => {
      if (!current) setPicked([])
      return !current
    })
  }, [])

  const toggleLodging = useCallback(kind => {
    setLodging(current => {
      if (kind === 'any') return ['any']
      const without = current.filter(k => k !== 'any')
      const next = without.includes(kind) ? without.filter(k => k !== kind) : [...without, kind]
      return next.length ? next : ['any']
    })
  }, [])

  const toggleDay = useCallback(key => {
    setDays(current => {
      const next = current.includes(key) ? current.filter(d => d !== key) : [...current, key]
      return next.length ? next : current
    })
  }, [])

  const setMinNights = useCallback(value => {
    const n = Number(value)
    setNightsMin(n)
    setNightsMax(current => (current < n ? n : current))
  }, [])

  const setMaxNights = useCallback(value => {
    const n = Number(value)
    setNightsMax(n)
    setNightsMin(current => (current > n ? n : current))
  }, [])

  const run = useCallback(async () => {
    if (!API) return
    if (!home.trim()) {
      setError('write where you are leaving from')
      return
    }
    if (!anywhere && !picked.length) {
      setError('pick at least one destination, or turn on "no matter"')
      return
    }
    setError('')
    setOpen(null)
    const params = {
      home: home.trim(),
      destinations: anywhere ? 'any' : picked,
      max_destinations: 8,
      window_start: dateFrom,
      window_end: dateTo,
      nights_min: nightsMin,
      nights_max: nightsMax,
      weekdays: days,
      lodging,
      estimates,
      adults: 1,
      max_requests: 60,
      min_interval: 0.8
    }
    if (budget.trim()) params.budget_total = Number(budget)
    try {
      setJob({ status: 'running', elapsed_seconds: 0 })
      const started = await API.rest('/search', { method: 'POST', body: params })
      setJobId(started.job_id)
    } catch (err) {
      setError(String(err && err.message ? err.message : err))
      setJob(null)
    }
  }, [home, picked, anywhere, dateFrom, dateTo, nightsMin, nightsMax, days, lodging, estimates, budget])

  const running = jobId !== null
  const result = job && job.result ? job.result : null
  const options = result && result.options ? result.options : []
  const stats = result && result.stats ? result.stats : null
  const tried = result && result.query && result.query.destinations ? result.query.destinations : []

  if (!presets) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center p-3 text-xs text-(--ui-text-secondary)',
      children: error || 'tripscout: loading…'
    })
  }

  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 overflow-auto p-3 text-xs',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between',
        children: [
          jsx('div', { className: 'text-sm font-medium', children: 'tripscout' }),
          jsx('div', {
            className: hint,
            children: presets.cache ? `${presets.cache.cached_entries} cached` : ''
          })
        ]
      }),

      // --- da dove parti: testo libero, lo interpreta il backend -------------
      jsx(Row, {
        caption: 'leaving from',
        children: jsxs('div', {
          className: 'flex flex-col gap-1',
          children: [
            jsxs('div', {
              children: [
                jsx('input', {
                  className: field,
                  value: home,
                  list: 'tripscout-homes',
                  placeholder: 'write a town, e.g. Prato',
                  onChange: event => setHome(event.target.value)
                }),
                jsx('datalist', {
                  id: 'tripscout-homes',
                  children: knownHomes.map(city =>
                    jsx('option', { value: city.city }, city.city)
                  )
                })
              ]
            }),
            jsx('div', {
              className: hint,
              children: 'the airports serving it and their train/bus cost are worked out for you'
            })
          ]
        })
      }),

      // --- dove andare: elenco piatto + "no matter" ---------------------------
      jsx(Row, {
        caption: 'where to',
        children: jsxs('div', {
          className: 'flex flex-col gap-1',
          children: [
            jsx('div', {
              className: 'flex flex-wrap gap-1',
              children: [
                jsx(Chip, {
                  on: anywhere,
                  title: 'try a shortlist of cheap European cities and let the price decide',
                  onClick: toggleAnywhere,
                  children: 'no matter'
                }),
                ...allCities.map(city =>
                  jsx(
                    Chip,
                    {
                      on: !anywhere && picked.includes(city.city),
                      title: `${city.airports.join(' / ')} · transfer ${city.transfer_cost}`,
                      onClick: () => togglePicked(city.city),
                      children: city.city
                    },
                    city.city
                  )
                )
              ]
            }),
            jsx('div', {
              className: hint,
              children: anywhere
                ? 'no matter: tries up to 8 cheap-first cities and ranks what comes back'
                : picked.length
                  ? `${picked.length} picked: ${picked.join(', ')}`
                  : 'pick at least one'
            })
          ]
        })
      }),

      // --- notti: intervallo con due slider ---------------------------------
      jsx(Row, {
        caption: `nights: ${nightsMin}–${nightsMax}`,
        children: jsxs('div', {
          className: 'flex flex-col gap-0.5',
          children: [
            jsx('input', {
              type: 'range',
              min: 1,
              max: 7,
              value: nightsMin,
              className: 'w-full',
              onChange: event => setMinNights(event.target.value)
            }),
            jsx('input', {
              type: 'range',
              min: 1,
              max: 7,
              value: nightsMax,
              className: 'w-full',
              onChange: event => setMaxNights(event.target.value)
            })
          ]
        })
      }),

      // --- partenza: giorni ammessi + intervallo di date ---------------------
      jsx(Row, {
        caption: 'leaving on',
        children: jsx('div', {
          className: 'flex flex-wrap gap-1',
          children: WEEKDAYS.map(day =>
            jsx(Chip, { on: days.includes(day.key), onClick: () => toggleDay(day.key), children: day.label }, day.key)
          )
        })
      }),

      jsxs('div', {
        className: 'grid grid-cols-2 gap-2',
        children: [
          jsx(Row, {
            caption: 'from date',
            children: jsx('input', {
              type: 'date',
              className: field,
              value: dateFrom,
              onChange: event => setDateFrom(event.target.value)
            })
          }),
          jsx(Row, {
            caption: 'to date',
            children: jsx('input', {
              type: 'date',
              className: field,
              value: dateTo,
              onChange: event => setDateTo(event.target.value)
            })
          })
        ]
      }),

      jsx(Row, {
        caption: 'sleep in',
        children: jsx('div', {
          className: 'flex flex-wrap gap-1',
          children: ['any', 'hostel', 'hotel', 'apartment'].map(kind =>
            jsx(Chip, { on: lodging.includes(kind), onClick: () => toggleLodging(kind), children: kind }, kind)
          )
        })
      }),

      jsxs('div', {
        className: 'flex items-end justify-between gap-2',
        children: [
          jsx(Row, {
            caption: 'budget EUR',
            children: jsx('input', {
              className: field,
              value: budget,
              placeholder: 'no limit',
              inputMode: 'numeric',
              onChange: event => setBudget(event.target.value)
            })
          }),
          jsx('label', {
            className: 'flex items-center gap-1 pb-1 text-[0.6875rem] text-(--ui-text-secondary)',
            children: [
              jsx('input', {
                type: 'checkbox',
                checked: estimates,
                onChange: event => setEstimates(event.target.checked)
              }),
              'food & tickets'
            ]
          }),
          jsx('button', {
            type: 'button',
            disabled: running,
            onClick: run,
            className: cn(
              'rounded border border-(--ui-accent) px-2 py-1 text-[0.6875rem] text-(--ui-accent)',
              running ? 'opacity-50' : 'hover:bg-(--chrome-action-hover)'
            ),
            children: running ? `searching… ${job ? job.elapsed_seconds.toFixed(0) : 0}s` : 'find trips'
          })
        ]
      }),

      error
        ? jsx('div', {
            className:
              'rounded border border-(--ui-stroke-secondary) p-2 text-[0.6875rem] text-(--ui-text-secondary)',
            children: error
          })
        : null,

      job && job.error
        ? jsx('div', {
            className: 'rounded border border-(--ui-stroke-secondary) p-2 text-[0.6875rem]',
            children: job.error
          })
        : null,

      stats
        ? jsx('div', {
            className: hint,
            children: `${stats.combinations_ranked} combinations · ${stats.requests_spent} requests · ${stats.cache_hits} cached · ${stats.elapsed_seconds}s`
          })
        : null,

      tried.length
        ? jsx('div', {
            className: hint,
            children: `tried: ${tried.join(', ')}`
          })
        : null,

      jsxs('div', {
        className: 'flex flex-col gap-1',
        children: [
          options.map((option, index) =>
            jsxs(
              'div',
              {
                className: cn(
                  'cursor-pointer rounded border border-(--ui-stroke-secondary) p-2',
                  index === 0 ? 'border-(--ui-accent)' : ''
                ),
                onClick: () => setOpen(open === index ? null : index),
                children: [
                  jsxs('div', {
                    className: 'flex items-baseline justify-between gap-2',
                    children: [
                      jsxs('div', {
                        className: 'flex flex-col',
                        children: [
                          jsx('div', { className: 'text-xs font-medium', children: option.city }),
                          jsx('div', {
                            className: 'text-[0.6875rem] text-(--ui-text-secondary)',
                            children: `${option.dates} · from ${option.from}`
                          })
                        ]
                      }),
                      jsxs('div', {
                        className: 'flex flex-col items-end',
                        children: [
                          jsx('div', { className: 'text-xs font-medium', children: option.total_text }),
                          jsx('div', { className: hint, children: option.lodging_kind })
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
            ? jsx('div', {
                className: 'text-[0.6875rem] text-(--ui-text-secondary)',
                children: 'nothing within those limits — widen the dates or the budget'
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
