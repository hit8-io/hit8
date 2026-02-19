import { defineField, defineType } from 'sanity'
import { HomeIcon } from '@sanity/icons'

export default defineType({
  name: 'home',
  title: 'Home Page',
  type: 'document',
  icon: HomeIcon,
  fields: [
    defineField({ name: 'hero', type: 'hero' }),
    defineField({
      name: 'features',
      type: 'array',
      of: [{ type: 'feature' }],
    }),
  ],
})
