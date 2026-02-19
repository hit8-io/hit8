import { defineField, defineType } from 'sanity'
import { StarIcon } from '@sanity/icons'

export default defineType({
  name: 'feature',
  title: 'Feature',
  type: 'object',
  icon: StarIcon,
  fields: [
    defineField({ name: 'title', type: 'string' }),
    defineField({ name: 'description', type: 'text' }),
    defineField({
      name: 'icon',
      type: 'string',
      options: {
        list: [
          { title: 'Eye (Transparency)', value: 'eye' },
          { title: 'Refresh (Repeatable)', value: 'refresh' },
          { title: 'Users (Human)', value: 'users' },
          { title: 'Target (Outcome)', value: 'target' },
          { title: 'Database (Fact Based)', value: 'database' },
          { title: 'Box (Tangible)', value: 'box' },
        ],
      },
    }),
  ],
})
