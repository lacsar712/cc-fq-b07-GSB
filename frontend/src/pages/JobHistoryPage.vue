<template>
  <q-page class="page-pad">
    <div class="row items-center q-mb-md">
      <div class="text-h5">作业历史</div>
      <q-space />
      <q-toggle
        v-model="includeArchived"
        label="含归档"
        left-label
        class="q-mr-md"
        @update:model-value="(v) => load(v)"
      />
      <q-btn flat icon="refresh" label="刷新" @click="load" :loading="loading" />
      <q-btn
        v-if="auth.role === 'bioops'"
        color="primary"
        class="q-ml-sm"
        label="新建作业"
        to="/jobs/new"
      />
    </div>

    <q-banner v-if="!includeArchived" dense rounded class="bg-grey-2 q-mb-md">
      默认历史不显示已归档作业；打开「含归档」可查看并进入详情。
    </q-banner>

    <q-table
      flat
      bordered
      row-key="id"
      :rows="rows"
      :columns="columns"
      :loading="loading"
      hide-pagination
      :pagination="{ rowsPerPage: 0 }"
    >
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-badge :color="statusColor(props.row.status)">
            {{ statusLabel(props.row.status) }}
          </q-badge>
          <q-badge v-if="props.row.is_archived" color="amber-9" text-color="white" class="q-ml-sm">
            已归档
          </q-badge>
        </q-td>
      </template>
      <template #body-cell-metrics="props">
        <q-td :props="props">
          <span v-if="props.row.metrics">
            Q={{ props.row.metrics.mean_quality ?? '—' }}
            · N={{ props.row.metrics.n_rate ?? '—' }}
            · reads={{ props.row.metrics.reads ?? '—' }}
          </span>
          <span v-else class="text-grey-6">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props">
          <q-btn dense flat color="primary" label="详情" :to="`/jobs/${props.row.id}`" />
          <q-btn
            v-if="canArchive(props.row)"
            dense
            flat
            color="amber-9"
            :label="archivingId === props.row.id ? '归档中…' : '归档'"
            :loading="archivingId === props.row.id"
            @click="onArchive(props.row)"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { archiveJob, listJobs } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const $q = useQuasar()
const loading = ref(false)
const rows = ref([])
const includeArchived = ref(false)
const archivingId = ref(null)

const columns = [
  { name: 'id', label: 'ID', field: 'id', align: 'left' },
  { name: 'sample_name', label: '样例', field: 'sample_name', align: 'left' },
  { name: 'status', label: '状态', field: 'status', align: 'left' },
  { name: 'created_by', label: '提交人', field: 'created_by', align: 'left' },
  { name: 'metrics', label: '指标摘要', field: 'metrics', align: 'left' },
  {
    name: 'created_at',
    label: '创建时间',
    field: 'created_at',
    align: 'left',
    format: (v) => (v ? new Date(v).toLocaleString() : ''),
  },
  { name: 'actions', label: '操作', field: 'actions', align: 'left' },
]

function statusLabel(s) {
  return { pending: '排队中', running: '运行中', success: '成功', failed: '失败' }[s] || s
}

function statusColor(s) {
  return { pending: 'grey', running: 'info', success: 'positive', failed: 'negative' }[s] || 'grey'
}

// 归档约定：仅运维、仅成功态、且尚未归档的作业可收进归档层
function canArchive(row) {
  return auth.role === 'bioops' && row.status === 'success' && !row.is_archived
}

async function load(includeArchivedValue = includeArchived.value) {
  loading.value = true
  try {
    rows.value = await listJobs(includeArchivedValue)
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

async function onArchive(row) {
  archivingId.value = row.id
  try {
    await archiveJob(row.id)
    $q.notify({ type: 'positive', message: `作业 #${row.id} 已收入归档层` })
    // 重新拉取：默认视图下该条会从列表消失；含归档视图下仍可见并带「已归档」标记
    await load()
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '归档失败' })
  } finally {
    archivingId.value = null
  }
}

onMounted(load)
</script>
