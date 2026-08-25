<script setup lang="ts">
import { computed } from 'vue'
import {
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElDivider,
  ElForm,
  ElFormItem,
  ElInput
} from 'element-plus'

import BundleLeafField from './BundleLeafField.vue'
import type { FiveStageFieldError } from '../../../stores/fiveStageExecution'
import {
  createDefaultCoolingZone,
  createDefaultEquipmentSystem,
  type EngineeringInputFormState
} from '../model/engineeringInputForm'
import { snakeToCamelField } from '../model/engineeringInputForm'

const props = defineProps<{
  modelValue: EngineeringInputFormState
  fieldError?: FiveStageFieldError | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: EngineeringInputFormState]
}>()

const form = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

function matchesFieldError(formKey: string): FiveStageFieldError | null {
  if (!props.fieldError?.formKey) return null
  return props.fieldError.formKey === formKey ? props.fieldError : null
}

function fieldErrorFor(formKey: string): { errorCode: string | null; errorMessage: string | null } {
  const match = matchesFieldError(formKey)
  return {
    errorCode: match?.code ?? null,
    errorMessage: match?.message ?? null
  }
}

function updateZonePlanning<K extends keyof EngineeringInputFormState['zonePlanning']>(
  key: K,
  value: EngineeringInputFormState['zonePlanning'][K]
): void {
  form.value = {
    ...form.value,
    zonePlanning: { ...form.value.zonePlanning, [key]: value }
  }
}

function updateCoolingZone(
  index: number,
  key: string,
  value: string | number | null
): void {
  const zones = [...form.value.coolingZones]
  const zone = { ...zones[index], [snakeToCamelField(key)]: value }
  zones[index] = zone
  form.value = { ...form.value, coolingZones: zones }
}

function updateEquipmentRoot(key: string, value: number | null): void {
  form.value = {
    ...form.value,
    equipment: { ...form.value.equipment, [snakeToCamelField(key)]: value }
  }
}

function updateEquipmentSystem(
  systemIndex: number,
  key: string,
  value: string | number | null
): void {
  const systems = [...form.value.equipment.systems]
  const system = { ...systems[systemIndex], [snakeToCamelField(key)]: value }
  systems[systemIndex] = system
  form.value = {
    ...form.value,
    equipment: { ...form.value.equipment, systems }
  }
}

function updateEquipmentZone(
  systemIndex: number,
  zoneIndex: number,
  key: string,
  value: string | number | null
): void {
  const systems = [...form.value.equipment.systems]
  const zones = [...systems[systemIndex].zones]
  zones[zoneIndex] = { ...zones[zoneIndex], [snakeToCamelField(key)]: value }
  systems[systemIndex] = { ...systems[systemIndex], zones }
  form.value = {
    ...form.value,
    equipment: { ...form.value.equipment, systems }
  }
}

function updateInstalledPower(
  key: string,
  value: number | null
): void {
  form.value = {
    ...form.value,
    installedPower: { ...form.value.installedPower, [snakeToCamelField(key)]: value }
  }
}

function updateInvestment(
  key: string,
  value: number | null
): void {
  form.value = {
    ...form.value,
    investment: { ...form.value.investment, [snakeToCamelField(key)]: value }
  }
}

function addCoolingZone(): void {
  form.value = {
    ...form.value,
    coolingZones: [...form.value.coolingZones, createDefaultCoolingZone()]
  }
}

function addEquipmentSystem(): void {
  form.value = {
    ...form.value,
    equipment: {
      ...form.value.equipment,
      systems: [...form.value.equipment.systems, createDefaultEquipmentSystem()]
    }
  }
}

const unmappedFieldError = computed(() => {
  if (!props.fieldError) return null
  if (props.fieldError.formKey) return null
  return props.fieldError
})
</script>

<template>
  <div class="engineering-input-bundle-form">
    <ElAlert
      v-if="unmappedFieldError"
      type="error"
      :closable="false"
      show-icon
      :title="`[${unmappedFieldError.code}] ${unmappedFieldError.message}`"
      :description="`字段路径: ${unmappedFieldError.fieldPath}`"
      class="engineering-input-bundle-form__alert"
    />

    <ElForm label-position="top">
      <ElCard shadow="never" class="engineering-input-bundle-form__section">
        <template #header>区域规划输入 (zone_planning_inputs)</template>
        <BundleLeafField
          label="日入库量"
          field-key="zonePlanning.dailyInboundMassKg"
          :model-value="form.zonePlanning.dailyInboundMassKg"
          unit="kg/day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.dailyInboundMassKg')"
          @update:model-value="updateZonePlanning('dailyInboundMassKg', $event as number | null)"
        />
        <BundleLeafField
          label="日工作时长"
          field-key="zonePlanning.workingTimeHPerDay"
          :model-value="form.zonePlanning.workingTimeHPerDay"
          unit="h/day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.workingTimeHPerDay')"
          @update:model-value="updateZonePlanning('workingTimeHPerDay', $event as number | null)"
        />
        <BundleLeafField
          label="成品储存天数"
          field-key="zonePlanning.finishedStorageDays"
          :model-value="form.zonePlanning.finishedStorageDays"
          unit="day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.finishedStorageDays')"
          @update:model-value="updateZonePlanning('finishedStorageDays', $event as number | null)"
        />
        <BundleLeafField
          label="包装储存天数"
          field-key="zonePlanning.packagingStorageDays"
          :model-value="form.zonePlanning.packagingStorageDays"
          unit="day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.packagingStorageDays')"
          @update:model-value="updateZonePlanning('packagingStorageDays', $event as number | null)"
        />
        <BundleLeafField
          label="预冷需求比例"
          field-key="zonePlanning.precoolingRequiredRatio"
          :model-value="form.zonePlanning.precoolingRequiredRatio"
          unit="ratio"
          type="number"
          :precision="3"
          :disabled="disabled"
          v-bind="fieldErrorFor('zonePlanning.precoolingRequiredRatio')"
          @update:model-value="updateZonePlanning('precoolingRequiredRatio', $event as number | null)"
        />
      </ElCard>

      <ElCard
        v-for="(zone, zoneIndex) in form.coolingZones"
        :key="`cooling-zone-${zoneIndex}`"
        shadow="never"
        class="engineering-input-bundle-form__section"
      >
        <template #header>冷负荷分区 {{ zoneIndex + 1 }} (cooling_load_inputs.zones)</template>
        <BundleLeafField
          label="分区编码"
          :field-key="`coolingZones.${zoneIndex}.zoneCode`"
          :model-value="zone.zoneCode"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.zoneCode`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'zone_code', $event)"
        />
        <BundleLeafField
          label="分区名称"
          :field-key="`coolingZones.${zoneIndex}.zoneName`"
          :model-value="zone.zoneName"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.zoneName`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'zone_name', $event)"
        />
        <BundleLeafField
          label="温区等级"
          :field-key="`coolingZones.${zoneIndex}.temperatureLevel`"
          :model-value="zone.temperatureLevel"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.temperatureLevel`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'temperature_level', $event)"
        />
        <BundleLeafField
          label="分区面积"
          :field-key="`coolingZones.${zoneIndex}.zoneArea`"
          :model-value="zone.zoneArea"
          unit="m2"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.zoneArea`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'zone_area', $event as number | null)"
        />
        <BundleLeafField
          label="库房高度"
          :field-key="`coolingZones.${zoneIndex}.roomHeight`"
          :model-value="zone.roomHeight"
          unit="m"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.roomHeight`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'room_height', $event as number | null)"
        />
        <BundleLeafField
          label="墙体面积"
          :field-key="`coolingZones.${zoneIndex}.wallArea`"
          :model-value="zone.wallArea"
          unit="m2"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.wallArea`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'wall_area', $event as number | null)"
        />
        <BundleLeafField
          label="屋顶面积"
          :field-key="`coolingZones.${zoneIndex}.roofArea`"
          :model-value="zone.roofArea"
          unit="m2"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.roofArea`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'roof_area', $event as number | null)"
        />
        <BundleLeafField
          label="地面面积"
          :field-key="`coolingZones.${zoneIndex}.floorArea`"
          :model-value="zone.floorArea"
          unit="m2"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.floorArea`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'floor_area', $event as number | null)"
        />
        <BundleLeafField
          label="室外设计温度"
          :field-key="`coolingZones.${zoneIndex}.outdoorDesignTemperature`"
          :model-value="zone.outdoorDesignTemperature"
          unit="C"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.outdoorDesignTemperature`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'outdoor_design_temperature', $event as number | null)"
        />
        <BundleLeafField
          label="室内设计温度"
          :field-key="`coolingZones.${zoneIndex}.roomDesignTemperature`"
          :model-value="zone.roomDesignTemperature"
          unit="C"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.roomDesignTemperature`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'room_design_temperature', $event as number | null)"
        />
        <BundleLeafField
          label="日运行小时"
          :field-key="`coolingZones.${zoneIndex}.operatingHoursPerDay`"
          :model-value="zone.operatingHoursPerDay"
          unit="h/day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.operatingHoursPerDay`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'operating_hours_per_day', $event as number | null)"
        />
        <BundleLeafField
          label="日产品处理量"
          :field-key="`coolingZones.${zoneIndex}.productMassPerDay`"
          :model-value="zone.productMassPerDay"
          unit="kg/day"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.productMassPerDay`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'product_mass_per_day', $event as number | null)"
        />
        <BundleLeafField
          label="产品入库温度"
          :field-key="`coolingZones.${zoneIndex}.productEntryTemperature`"
          :model-value="zone.productEntryTemperature"
          unit="C"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.productEntryTemperature`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'product_entry_temperature', $event as number | null)"
        />
        <BundleLeafField
          label="产品目标温度"
          :field-key="`coolingZones.${zoneIndex}.productTargetTemperature`"
          :model-value="zone.productTargetTemperature"
          unit="C"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.productTargetTemperature`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'product_target_temperature', $event as number | null)"
        />
        <BundleLeafField
          label="冷却时长"
          :field-key="`coolingZones.${zoneIndex}.coolingDuration`"
          :model-value="zone.coolingDuration"
          unit="h"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.coolingDuration`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'cooling_duration', $event as number | null)"
        />
        <BundleLeafField
          label="墙体传热系数"
          :field-key="`coolingZones.${zoneIndex}.uValueWall`"
          :model-value="zone.uValueWall"
          unit="W/(m2·K)"
          type="number"
          :precision="3"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.uValueWall`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'u_value_wall', $event as number | null)"
        />
        <BundleLeafField
          label="屋顶传热系数"
          :field-key="`coolingZones.${zoneIndex}.uValueRoof`"
          :model-value="zone.uValueRoof"
          unit="W/(m2·K)"
          type="number"
          :precision="3"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.uValueRoof`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'u_value_roof', $event as number | null)"
        />
        <BundleLeafField
          label="地面传热系数"
          :field-key="`coolingZones.${zoneIndex}.uValueFloor`"
          :model-value="zone.uValueFloor"
          unit="W/(m2·K)"
          type="number"
          :precision="3"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.uValueFloor`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'u_value_floor', $event as number | null)"
        />
        <BundleLeafField
          label="产品比热"
          :field-key="`coolingZones.${zoneIndex}.productSpecificHeat`"
          :model-value="zone.productSpecificHeat"
          unit="kJ/(kg·K)"
          type="number"
          :precision="2"
          :disabled="disabled"
          v-bind="fieldErrorFor(`coolingZones.${zoneIndex}.productSpecificHeat`)"
          @update:model-value="updateCoolingZone(zoneIndex, 'product_specific_heat', $event as number | null)"
        />
      </ElCard>
      <ElButton :disabled="disabled" @click="addCoolingZone">添加冷负荷分区</ElButton>

      <ElDivider />

      <ElCard shadow="never" class="engineering-input-bundle-form__section">
        <template #header>设备输入 (equipment_inputs)</template>
        <BundleLeafField
          label="冷凝温度"
          field-key="equipment.condensingTemperatureC"
          :model-value="form.equipment.condensingTemperatureC"
          unit="C"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('equipment.condensingTemperatureC')"
          @update:model-value="updateEquipmentRoot('condensing_temperature_c', $event as number | null)"
        />

        <div
          v-for="(system, systemIndex) in form.equipment.systems"
          :key="`equipment-system-${systemIndex}`"
          class="engineering-input-bundle-form__nested"
        >
          <h4>系统 {{ systemIndex + 1 }}</h4>
          <BundleLeafField
            label="系统编码"
            :field-key="`equipment.systems.${systemIndex}.systemCode`"
            :model-value="system.systemCode"
            :disabled="disabled"
            v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.systemCode`)"
            @update:model-value="updateEquipmentSystem(systemIndex, 'system_code', $event)"
          />
          <BundleLeafField
            label="系统名称"
            :field-key="`equipment.systems.${systemIndex}.systemName`"
            :model-value="system.systemName"
            :disabled="disabled"
            v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.systemName`)"
            @update:model-value="updateEquipmentSystem(systemIndex, 'system_name', $event)"
          />
          <BundleLeafField
            label="设计蒸发温度"
            :field-key="`equipment.systems.${systemIndex}.designEvaporatingTemperature`"
            :model-value="system.designEvaporatingTemperature"
            unit="C"
            type="number"
            :disabled="disabled"
            v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.designEvaporatingTemperature`)"
            @update:model-value="updateEquipmentSystem(systemIndex, 'design_evaporating_temperature', $event as number | null)"
          />
          <div
            v-for="(eqZone, zoneIndex) in system.zones"
            :key="`equipment-zone-${systemIndex}-${zoneIndex}`"
            class="engineering-input-bundle-form__nested"
          >
            <h5>分区 {{ zoneIndex + 1 }}</h5>
            <BundleLeafField
              label="分区编码"
              :field-key="`equipment.systems.${systemIndex}.zones.${zoneIndex}.zoneCode`"
              :model-value="eqZone.zoneCode"
              :disabled="disabled"
              v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.zones.${zoneIndex}.zoneCode`)"
              @update:model-value="updateEquipmentZone(systemIndex, zoneIndex, 'zone_code', $event)"
            />
            <BundleLeafField
              label="分区名称"
              :field-key="`equipment.systems.${systemIndex}.zones.${zoneIndex}.zoneName`"
              :model-value="eqZone.zoneName"
              :disabled="disabled"
              v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.zones.${zoneIndex}.zoneName`)"
              @update:model-value="updateEquipmentZone(systemIndex, zoneIndex, 'zone_name', $event)"
            />
            <BundleLeafField
              label="蒸发器数量"
              :field-key="`equipment.systems.${systemIndex}.zones.${zoneIndex}.evaporatorCount`"
              :model-value="eqZone.evaporatorCount"
              unit="count"
              type="number"
              :precision="0"
              :disabled="disabled"
              v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.zones.${zoneIndex}.evaporatorCount`)"
              @update:model-value="updateEquipmentZone(systemIndex, zoneIndex, 'evaporator_count', $event as number | null)"
            />
            <BundleLeafField
              label="化霜方式"
              :field-key="`equipment.systems.${systemIndex}.zones.${zoneIndex}.defrostMethod`"
              :model-value="eqZone.defrostMethod"
              :disabled="disabled"
              v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.zones.${zoneIndex}.defrostMethod`)"
              @update:model-value="updateEquipmentZone(systemIndex, zoneIndex, 'defrost_method', $event)"
            />
            <BundleLeafField
              label="设计冷负荷"
              :field-key="`equipment.systems.${systemIndex}.zones.${zoneIndex}.designCoolingLoadKwR`"
              :model-value="eqZone.designCoolingLoadKwR"
              unit="kW(r)"
              type="number"
              :disabled="disabled"
              v-bind="fieldErrorFor(`equipment.systems.${systemIndex}.zones.${zoneIndex}.designCoolingLoadKwR`)"
              @update:model-value="updateEquipmentZone(systemIndex, zoneIndex, 'design_cooling_load_kw_r', $event as number | null)"
            />
          </div>
        </div>
        <ElButton :disabled="disabled" @click="addEquipmentSystem">添加设备系统</ElButton>
      </ElCard>

      <ElCard shadow="never" class="engineering-input-bundle-form__section">
        <template #header>装机功率输入 (installed_power_inputs)</template>
        <BundleLeafField
          label="压缩机输入功率"
          field-key="installedPower.compressorInputPowerKwE"
          :model-value="form.installedPower.compressorInputPowerKwE"
          unit="kW(e)"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('installedPower.compressorInputPowerKwE')"
          @update:model-value="updateInstalledPower('compressor_input_power_kw_e', $event as number | null)"
        />
        <BundleLeafField
          label="蒸发风机功率"
          field-key="installedPower.evaporatorFanPowerKwE"
          :model-value="form.installedPower.evaporatorFanPowerKwE"
          unit="kW(e)"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('installedPower.evaporatorFanPowerKwE')"
          @update:model-value="updateInstalledPower('evaporator_fan_power_kw_e', $event as number | null)"
        />
        <BundleLeafField
          label="冷凝风机功率"
          field-key="installedPower.condenserFanPowerKwE"
          :model-value="form.installedPower.condenserFanPowerKwE"
          unit="kW(e)"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('installedPower.condenserFanPowerKwE')"
          @update:model-value="updateInstalledPower('condenser_fan_power_kw_e', $event as number | null)"
        />
      </ElCard>

      <ElCard shadow="never" class="engineering-input-bundle-form__section">
        <template #header>投资估算输入 (investment_inputs)</template>
        <ElFormItem>
          <ElCheckbox
            v-model="form.confirmPersistedLineage"
            :disabled="disabled"
          >
            确认使用持久化上游结果绑定投资输入 (persisted_upstream_confirmed)
          </ElCheckbox>
        </ElFormItem>
        <BundleLeafField
          label="总建筑面积"
          field-key="investment.totalAreaM2"
          :model-value="form.investment.totalAreaM2"
          unit="m2"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('investment.totalAreaM2')"
          @update:model-value="updateInvestment('total_area_m2', $event as number | null)"
        />
        <BundleLeafField
          label="冷藏面积"
          field-key="investment.refrigeratedAreaM2"
          :model-value="form.investment.refrigeratedAreaM2"
          unit="m2"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('investment.refrigeratedAreaM2')"
          @update:model-value="updateInvestment('refrigerated_area_m2', $event as number | null)"
        />
        <BundleLeafField
          label="冷冻面积"
          field-key="investment.frozenAreaM2"
          :model-value="form.investment.frozenAreaM2"
          unit="m2"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('investment.frozenAreaM2')"
          @update:model-value="updateInvestment('frozen_area_m2', $event as number | null)"
        />
        <BundleLeafField
          label="货位数"
          field-key="investment.positionCount"
          :model-value="form.investment.positionCount"
          unit="count"
          type="number"
          :precision="0"
          :disabled="disabled"
          v-bind="fieldErrorFor('investment.positionCount')"
          @update:model-value="updateInvestment('position_count', $event as number | null)"
        />
        <BundleLeafField
          label="总装机功率"
          field-key="investment.totalPowerKw"
          :model-value="form.investment.totalPowerKw"
          unit="kW(e)"
          type="number"
          :disabled="disabled"
          v-bind="fieldErrorFor('investment.totalPowerKw')"
          @update:model-value="updateInvestment('total_power_kw', $event as number | null)"
        />
      </ElCard>

      <ElCard shadow="never" class="engineering-input-bundle-form__section">
        <template #header>系数上下文 (coefficient_context)</template>
        <ElFormItem label="系数上下文 ID">
          <ElInput
            v-model="form.coefficientContext.coefficientContextId"
            :disabled="disabled"
          />
        </ElFormItem>
        <ElFormItem label="已批准修订 ID（逗号分隔）">
          <ElInput
            :model-value="form.coefficientContext.approvedRevisionIds.join(', ')"
            :disabled="disabled"
            @update:model-value="form.coefficientContext.approvedRevisionIds = String($event).split(',').map((s) => s.trim()).filter(Boolean)"
          />
        </ElFormItem>
      </ElCard>
    </ElForm>
  </div>
</template>

<style scoped>
.engineering-input-bundle-form {
  display: grid;
  gap: 16px;
}

.engineering-input-bundle-form__section {
  margin-bottom: 8px;
}

.engineering-input-bundle-form__nested {
  margin: 12px 0;
  padding: 12px;
  border: 1px dashed #d0d7e2;
  border-radius: 6px;
  background: #fafbfc;
}

.engineering-input-bundle-form__nested h4,
.engineering-input-bundle-form__nested h5 {
  margin: 0 0 8px;
  color: #163f68;
}

.engineering-input-bundle-form__alert {
  margin-bottom: 8px;
}
</style>
