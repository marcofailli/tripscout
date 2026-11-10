/**
 * tripscout — pannello Hermes Desktop.
 *
 * Un pannello, nient'altro: parte da una città ("Prato"), propone le
 * destinazioni a chip, filtra per tipo di alloggio e mostra il viaggio intero
 * — volo, alloggio, adduzione, transfer — con la stima di cibo e attrazioni.
 *
 * Il lavoro vero lo fa il backend (`dashboard/plugin_api.py`), che gira lo
 * stesso motore dei tool dell'agente. Qui non c'è nessuna logica di prezzo:
 * il pannello non può divergere da quello che risponde in chat.
 */

import { cn, host, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useCallback, useEffect, useMemo, useState } from 'react'

const ID = 'tripscout'

let API = null

const chipBase =
  'inline-flex items-center rounded-full border px-2 py-0.5 text-[0.6875rem] transition-colors'
const chipOff =
  'border-(--ui-stroke-secondary) text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)'
const chipOn = 'border-(--ui-accent) text-(--ui-accent) bg-(--chrome-action-hover)'
const label = 'text-[0.6875rem] uppercase tracking-wide text-(--ui-text-quaternary)'
const field =
  'w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-1.5 py-1 text-xs text-foreground'

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
    children: [
      jsx('div', { className: label, children: caption }),
      children
    ]
  })
}

function Breakdown({ option }) {
  const est = option.estimate
  return jsxs('div', {
    className: 'mt-1 flex flex-col gap-0.5 border-l pl-2 text-[0.6875rem] text-(--ui-text-secondary)',
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
        className: 'text-(--ui-text-quaternary)',
        children: `${option.airlines.join(', ') || 'flight'} · ${option.flight_departure || ''}`
      })
    ]
  })
}

function TripscoutPane() {
  const gateway = useValue(host.state.gateway)
  const [presets, setPresets] = useState(null)
  const [home, setHome] = useState('Prato')
  const [region, setRegion] = useState('east')
  const [picked, setPicked] = useState(['Budapest', 'Vienna', 'Praga'])
  const [lodging, setLodging] = useState(['any'])
  const [weekends, setWeekends] = useState(2)
  const [nightsMin, setNightsMin] = useState(2)
  const [nightsMax, setNightsMax] = useState(3)
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

  // un solo timer, spento appena il job finisce
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

  const destinations = useMemo(() => (presets ? presets.destinations : []), [presets])
  const regions = useMemo(() => (presets ? presets.regions : []), [presets])
  const homes = useMemo(() => (presets ? presets.home_cities : []), [presets])

  const togglePicked = useCallback(name => {
    setPicked(current =>
      current.includes(name) ? current.filter(c => c !== name) : [...current, name].slice(0, 10)
    )
  }, [])

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
    setError('')
    setOpen(null)
    const params = {
      home,
      destinations: picked,
      weekends,
      nights_min: nightsMin,
      nights_max: nightsMax,
      weekdays: ['thursday', 'friday'],
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
  }, [home, picked, weekends, nightsMin, nightsMax, lodging, estimates, budget])

  const running = jobId !== null
  const result = job && job.result ? job.result : null
  const options = result && result.options ? result.options : []
  const stats = result && result.stats ? result.stats : null

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
            className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
            children: presets.cache ? `${presets.cache.cached_entries} cached` : ''
          })
        ]
      }),

      jsx(Row, {
        caption: 'leaving from',
        children: jsx('select', {
          className: field,
          value: home,
          onChange: event => setHome(event.target.value),
          children: homes.map(entry =>
            jsx('option', { value: entry.city, children: entry.city }, entry.city)
          )
        })
      }),

      jsxs('div', {
        className: 'flex flex-wrap gap-1 text-[0.6875rem] text-(--ui-text-quaternary)',
        children: (homes.find(entry => entry.city === home) || { airports: [] }).airports.map(entry =>
          jsx('span', { children: `${entry.airport} ~${entry.access_cost.toFixed(0)}` }, entry.airport)
        )
      }),

      jsx(Row, {
        caption: 'where to',
        children: jsxs('div', {
          className: 'flex flex-col gap-1',
          children: [
            jsx('div', {
              className: 'flex flex-wrap gap-1',
              children: regions.map(name =>
                jsx(
                  Chip,
                  {
                    on: region === name,
                    onClick: () => setRegion(name),
                    children: name
                  },
                  name
                )
              )
            }),
            jsx('div', {
              className: 'flex max-h-40 flex-wrap gap-1 overflow-auto',
              children: destinations
                .filter(entry => entry.region === region)
                .map(entry =>
                  jsx(
                    Chip,
                    {
                      on: picked.includes(entry.city),
                      title: `${entry.airports.join(' / ')} · transfer ${entry.transfer_cost}`,
                      onClick: () => togglePicked(entry.city),
                      children: entry.city
                    },
                    entry.city
                  )
                )
            }),
            jsx('div', {
              className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
              children: picked.length ? `${picked.length} selected: ${picked.join(', ')}` : 'pick at least one'
            })
          ]
        })
      }),

      jsxs('div', {
        className: 'grid grid-cols-3 gap-2',
        children: [
          jsx(Row, {
            caption: 'weekends',
            children: jsx('select', {
              className: field,
              value: weekends,
              onChange: event => setWeekends(Number(event.target.value)),
              children: [1, 2, 3, 4].map(n => jsx('option', { value: n, children: n }, n))
            })
          }),
          jsx(Row, {
            caption: 'nights',
            children: jsxs('div', {
              className: 'flex items-center gap-1',
              children: [
                jsx('select', {
                  className: field,
                  value: nightsMin,
                  onChange: event => setNightsMin(Number(event.target.value)),
                  children: [1, 2, 3, 4, 5].map(n => jsx('option', { value: n, children: n }, n))
                }),
                jsx('select', {
                  className: field,
                  value: nightsMax,
                  onChange: event => setNightsMax(Number(event.target.value)),
                  children: [1, 2, 3, 4, 5, 6].map(n => jsx('option', { value: n, children: n }, n))
                })
              ]
            })
          }),
          jsx(Row, {
            caption: 'budget EUR',
            children: jsx('input', {
              className: field,
              value: budget,
              placeholder: 'no limit',
              inputMode: 'numeric',
              onChange: event => setBudget(event.target.value)
            })
          })
        ]
      }),

      jsx(Row, {
        caption: 'sleep in',
        children: jsx('div', {
          className: 'flex flex-wrap gap-1',
          children: ['any', 'hostel', 'hotel', 'apartment'].map(kind =>
            jsx(
              Chip,
              { on: lodging.includes(kind), onClick: () => toggleLodging(kind), children: kind },
              kind
            )
          )
        })
      }),

      jsxs('div', {
        className: 'flex items-center justify-between',
        children: [
          jsxs('label', {
            className: 'flex items-center gap-1 text-[0.6875rem] text-(--ui-text-secondary)',
            children: [
              jsx('input', {
                type: 'checkbox',
                checked: estimates,
                onChange: event => setEstimates(event.target.checked)
              }),
              'food & tickets estimate'
            ]
          }),
          jsx('button', {
            type: 'button',
            disabled: running || !picked.length,
            onClick: run,
            className: cn(
              'rounded border border-(--ui-accent) px-2 py-1 text-[0.6875rem] text-(--ui-accent)',
              running || !picked.length ? 'opacity-50' : 'hover:bg-(--chrome-action-hover)'
            ),
            children: running
              ? `searching… ${job ? job.elapsed_seconds.toFixed(0) : 0}s`
              : 'find trips'
          })
        ]
      }),

      error
        ? jsx('div', { className: 'rounded border border-(--ui-stroke-secondary) p-2 text-[0.6875rem] text-(--ui-text-secondary)', children: error })
        : null,

      job && job.error
        ? jsx('div', { className: 'rounded border border-(--ui-stroke-secondary) p-2 text-[0.6875rem]', children: job.error })
        : null,

      stats
        ? jsx('div', {
            className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
            children: `${stats.combinations_ranked} combinations · ${stats.requests_spent} requests · ${stats.cache_hits} cached · ${stats.elapsed_seconds}s`
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
                          jsx('div', {
                            className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
                            children: option.lodging_kind
                          })
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
                children: 'no trip within those constraints — widen the dates or the budget'
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
